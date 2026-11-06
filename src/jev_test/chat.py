"""Chat-completions protocol for models without System One support.

System One serves TypeSafe models only; `POST /api/v1/systemone` rejects others with
"Model <id> does not exist". To score such a model on the same examples, this module asks
the same question over `POST /api/v1/chat/completions` with a strict JSON schema.

Differences from the System One protocol, which matter when comparing scores:

- The answer is generated text parsed as JSON, not a typed decision.
- Multi-label tasks return a label set directly, so there are no per-label probabilities and
  no threshold: `--threshold` does not apply, and probability-based analysis is unavailable.
- Task instructions, label descriptions, truncation, and gold-label isolation are unchanged.
- The question differs on multi-label tasks: `chat` appends "Select every option that
  applies, or none." and lists bare numbered options, whereas System One asks one yes/no
  question per label ("Does this label apply: <description>?") with true/false criterion
  sentences. `chat-perlabel` (multi-label tasks only) is the control for that difference: it
  asks System One's per-label question and criteria for every label, answered as one boolean
  per label in a strict JSON schema.
"""

import json

from jev_test.questions import INSTRUCTIONS, truncate
from jev_test.tasks import get_task

CHAT_PROTOCOL_VERSION = "lexglue-chat-json-v1"
CHAT_PERLABEL_PROTOCOL_VERSION = "lexglue-chat-perlabel-v1"
SYSTEM_PROMPT = (
    "You classify legal documents. Answer only with JSON matching the provided schema. "
    "Base the answer solely on the document and the numbered options."
)


def schema(task_name: str, option_count: int) -> dict:
    task = get_task(task_name)
    indices = list(range(option_count))
    if task.multilabel:
        properties = {
            "labels": {
                "type": "array",
                "items": {"type": "integer", "enum": indices},
                "description": "Every applicable option number; empty if none applies.",
            }
        }
        required = ["labels"]
    else:
        properties = {"label": {"type": "integer", "enum": indices}}
        required = ["label"]
    return {
        "name": f"lexglue_{task_name}",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def build_chat_request(row: dict, model: str, max_chars: int) -> tuple[dict, dict]:
    task = get_task(row["task"])
    text, truncated = truncate(row["text"], max_chars)
    options = row["endings"] if task.name == "case_hold" else task.descriptions
    listing = "\n".join(f"{index}: {option}" for index, option in enumerate(options))
    instruction = INSTRUCTIONS[task.name]
    if task.multilabel:
        instruction += " Select every option that applies, or none."
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{instruction}\n\nOptions:\n{listing}\n\nDocument:\n{text}",
            },
        ],
        "response_format": {"type": "json_schema", "json_schema": schema(task.name, len(options))},
        "usage": {"include": True},
    }
    return payload, {
        "original_chars": len(row["text"]),
        "sent_chars": len(text),
        "truncated": truncated,
    }


def perlabel_question(description: str) -> tuple[str, str, str]:
    """System One's per-label question and criteria (`questions.build_request`)."""
    return (
        f"Does this label apply: {description}?",
        f"The label '{description}' applies to this document.",
        f"The label '{description}' does not apply to this document.",
    )


def build_chat_perlabel_request(row: dict, model: str, max_chars: int) -> tuple[dict, dict]:
    task = get_task(row["task"])
    if not task.multilabel:
        raise ValueError("chat-perlabel applies to multi-label tasks only")
    text, truncated = truncate(row["text"], max_chars)
    lines, properties = [], {}
    for index, description in enumerate(task.descriptions):
        question, true, false = perlabel_question(description)
        lines.append(f"label_{index}: {question} true: {true} false: {false}")
        properties[f"label_{index}"] = {"type": "boolean", "description": question}
    content = (
        f"{INSTRUCTIONS[task.name]}\n\nAnswer every question below with true or false, "
        f"each on its own.\n\nQuestions:\n" + "\n".join(lines) + f"\n\nDocument:\n{text}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": f"lexglue_{task.name}_perlabel",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            },
        },
        "usage": {"include": True},
    }
    return payload, {
        "original_chars": len(row["text"]),
        "sent_chars": len(text),
        "truncated": truncated,
    }


def chat_answer(response: dict) -> dict:
    if not isinstance(response.get("model"), str) or not response["model"]:
        raise ValueError("Chat response is missing the resolved model ID")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Chat response has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("Chat response has no message")
    if message.get("refusal"):
        raise ValueError("Model refused to answer")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Chat response has empty content")
    try:
        answer = json.loads(content)
    except ValueError as error:
        raise ValueError("Chat response content is not JSON") from error
    if not isinstance(answer, dict):
        raise ValueError("Chat response content is not a JSON object")
    return answer


def parse_chat_perlabel_response(task_name: str, response: dict, threshold: float):
    """Strict parse: every label must be answered with a JSON boolean."""
    task = get_task(task_name)
    answer = chat_answer(response)
    expected = {f"label_{i}" for i in range(len(task.codes))}
    if set(answer) != expected:
        raise ValueError("Chat answer has missing or unexpected label keys")
    if any(type(answer[k]) is not bool for k in expected):
        raise ValueError("Chat answer values must be booleans")
    return [i for i in range(len(task.codes)) if answer[f"label_{i}"]], {}


def normalize_usage(body: dict) -> dict:
    """Map chat usage onto the fields the report sums."""
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return body
    body = dict(body)
    body["usage"] = dict(usage)
    body["usage"].setdefault("input_tokens", usage.get("prompt_tokens"))
    body["usage"].setdefault("output_tokens", usage.get("completion_tokens"))
    return body


def parse_chat_response(task_name: str, response: dict, threshold: float) -> tuple[list, dict]:
    """Strict parse: a malformed or refused answer raises instead of becoming a default.

    Repeated labels are collapsed, not rejected: they name the same set, and OpenAI's strict
    schema mode forbids `uniqueItems`, so the schema cannot prevent them."""
    task = get_task(task_name)
    answer = chat_answer(response)
    key = "labels" if task.multilabel else "label"
    if key not in answer:
        raise ValueError(f"Chat answer is missing '{key}'")
    value = answer[key]
    labels = value if task.multilabel else [value]
    if not isinstance(labels, list):
        raise ValueError("Chat answer labels must be a list")
    if task.multilabel:
        labels = list(dict.fromkeys(labels))
    return task.validate_labels(labels), {}
