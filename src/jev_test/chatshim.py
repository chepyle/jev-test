"""A local System One endpoint backed by a chat model, for scoring chat models on Kev's suites.

Kev's `kev.benchmark --remote <url>` scores any server that answers `POST <url>/v1/systemone`.
This shim translates each such request into one OpenRouter chat-completions call with a strict
JSON schema (one property per question) and returns the answer in System One shape.

Protocol differences from System One, which matter when comparing scores:

- A chat answer is a single choice, so every distribution is one-hot (probability 1 on the
  chosen option). Accuracy is comparable; ECE, Brier, NLL and selective coverage are not.
- The state is rendered as labelled text the same way Kev's server renders it.
- Only the state, instructions and criteria reach the model: Kev's `api_request` strips labels.

Answers are cached on disk by request hash, so a crashed or repeated benchmark replays them
without new calls, and a client-side retry of a slow request does not pay twice.

    uv run python -m jev_test.chatshim --model openai/gpt-5.6-luna \
        --cache results/kev-suites/luna-cache
"""

import argparse
import hashlib
import json
import os
import random
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from jev_test.client import CHAT_ENDPOINT, RETRYABLE, THROTTLED

SHIM_PROTOCOL_VERSION = "kev-chat-json-v1"
SYSTEM_PROMPT = (
    "You answer typed questions about the given input. Answer only with JSON matching the "
    "provided schema. Base each answer solely on the input and the listed options."
)


def render(value, indent: int = 0) -> str:
    """Kev's state rendering (kev.api.render): field names kept as labels."""
    pad = "  " * indent
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(f"{pad}- {render(x, indent + 1).lstrip()}" for x in value)
    return "\n".join(
        f"{pad}{k}:\n{render(x, indent + 1)}"
        if isinstance(x, (dict, list))
        else f"{pad}{k}: {render(x)}"
        for k, x in value.items()
    )


def option_keys(question: dict) -> list[str]:
    """Answer keys as Kev names them: criteria (choice), false/true (noul), level index (score)."""
    if question["type"] == "choice":
        return list(question["criteria"])
    if question["type"] == "noul":
        return ["false", "true"]
    return [str(i) for i in range(len(question["criteria"]))]


def describe(qid: str, question: dict) -> str:
    lines = [f"Question '{qid}' ({question['type']}): {question['instructions']}"]
    criteria = question.get("criteria")
    if question["type"] == "choice":
        lines.append("Options:")
        lines += [
            f"- {k}" + (f": {render(v)}" if v not in (None, "") else "")
            for k, v in criteria.items()
        ]
    elif question["type"] == "noul":
        lines.append("Answer true or false.")
        if criteria:
            lines += [f"- {k}: {render(v)}" for k, v in criteria.items()]
    else:
        lines.append("Levels (answer with the level number):")
        lines += [f"- {i}: {render(v)}" for i, v in enumerate(criteria)]
    return "\n".join(lines)


def build_chat_request(request: dict, model: str) -> dict:
    questions = request["questions"]
    properties = {}
    for qid, q in questions.items():
        if q["type"] == "noul":
            properties[qid] = {"type": "boolean"}
        elif q["type"] == "score":
            properties[qid] = {"type": "integer", "enum": list(range(len(q["criteria"])))}
        else:
            properties[qid] = {"type": "string", "enum": option_keys(q)}
    listing = "\n\n".join(describe(qid, q) for qid, q in questions.items())
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Input:\n{render(request['state'])}\n\n{listing}"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "decisions",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(questions),
                    "additionalProperties": False,
                },
            },
        },
        "usage": {"include": True},
    }


def to_system_one(request: dict, body: dict) -> dict:
    """Strict parse of the chat answer into one-hot System One answers; malformed answers raise."""
    message = body["choices"][0]["message"]
    if message.get("refusal"):
        raise ValueError("model refused")
    answer = json.loads(message["content"])
    answers = {}
    for qid, q in request["questions"].items():
        value = answer[qid]
        if q["type"] == "noul":
            if not isinstance(value, bool):
                raise ValueError(f"{qid}: expected boolean")
            answers[qid] = {"type": "noul", "noul": 1.0 if value else 0.0}
            continue
        keys = option_keys(q)
        chosen = str(value)
        if chosen not in keys:
            raise ValueError(f"{qid}: {chosen!r} is not an option")
        answers[qid] = {
            "type": q["type"],
            "choice": chosen,
            "probabilities": {k: 1.0 if k == chosen else 0.0 for k in keys},
        }
    usage = body.get("usage") or {}
    return {
        "model": body["model"],
        "answers": answers,
        "usage": {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        },
        "cost": usage.get("cost"),
    }


class Shim:
    def __init__(self, model: str, cache: Path, api_key: str, attempts: int = 8):
        self.model, self.cache, self.api_key, self.attempts = model, cache, api_key, attempts
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = httpx.Client(timeout=300)
        self.lock = threading.Lock()

    def incident(self, text: str) -> None:
        with self.lock, (self.cache / "incidents.log").open("a") as log:
            log.write(f"{datetime.now(UTC).isoformat()} {text}\n")

    def answer(self, request: dict) -> dict:
        request = {"state": request["state"], "questions": request["questions"]}
        key = hashlib.sha256(
            json.dumps([SHIM_PROTOCOL_VERSION, self.model, request], sort_keys=True).encode()
        ).hexdigest()
        path = self.cache / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        payload = build_chat_request(request, self.model)
        last = None
        for attempt in range(self.attempts):
            try:
                response = self.http.post(
                    CHAT_ENDPOINT, json=payload, headers={"Authorization": f"Bearer {self.api_key}"}
                )
                if response.status_code == 200:
                    result = to_system_one(request, response.json())
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(result))
                    tmp.replace(path)
                    return result
                last = f"HTTP {response.status_code}: {response.text[:200]}"
                if response.status_code not in RETRYABLE:
                    break
            except (httpx.TransportError, ValueError, KeyError, IndexError, TypeError) as error:
                last = f"{type(error).__name__}: {error}"
            status = last.split(":")[0]
            throttled = any(status == f"HTTP {code}" for code in THROTTLED)
            delay = (30 if throttled else 2) * 2**attempt * (1 + random.random() / 2)
            self.incident(f"attempt {attempt + 1} {last} -> sleep {delay:.0f}s")
            time.sleep(delay)
        self.incident(f"gave up {key}: {last}")
        raise RuntimeError(last)


def serve(shim: Shim, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path.rstrip("/") != "/v1/systemone":
                self.send_error(404)
                return
            try:
                request = json.loads(self.rfile.read(int(self.headers["content-length"])))
                body, status = json.dumps(shim.answer(request)).encode(), 200
            except Exception as error:  # surfaced to kev.benchmark as a failed request
                body, status = json.dumps({"error": str(error)}).encode(), 502
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        parser.error("Set OPENROUTER_API_KEY")
    server = serve(Shim(args.model, args.cache, key), args.port)
    print(f"serving {args.model} on http://127.0.0.1:{args.port}/v1/systemone", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
