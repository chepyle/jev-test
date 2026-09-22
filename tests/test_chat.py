import asyncio
import json

import httpx
import pytest

from jev_test.chat import build_chat_request, parse_chat_response
from jev_test.client import CHAT_ENDPOINT, DEFAULT_ENDPOINT
from jev_test.runner import run_benchmark
from jev_test.storage import read_jsonl

MODEL = "openai/test-chat-model"


def fake_chat_response(request, model=MODEL):
    payload = json.loads(request.content)
    schema = payload["response_format"]["json_schema"]["schema"]
    answer = {"labels": [0]} if "labels" in schema["properties"] else {"label": 0}
    return {
        "id": "chat-fixture",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": json.dumps(answer)}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 5, "cost": 0.002},
    }


def test_request_carries_options_and_schema_but_never_gold():
    row = {
        "id": "ledgar/0",
        "task": "ledgar",
        "index": 0,
        "text": "The tenant shall pay rent monthly.",
        "gold": [7],
    }
    payload, info = build_chat_request(row, MODEL, 48_000)
    body = json.dumps(payload)
    assert '"gold"' not in body and '"7"' not in payload["messages"][1]["content"][:40]
    schema = payload["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["properties"]["label"]["enum"][:3] == [0, 1, 2]
    assert row["text"] in payload["messages"][1]["content"]
    assert info["truncated"] is False


def test_multilabel_schema_allows_the_empty_set():
    row = {"id": "unfair_tos/0", "task": "unfair_tos", "index": 0, "text": "A clause.", "gold": []}
    payload, _ = build_chat_request(row, MODEL, 48_000)
    labels = payload["response_format"]["json_schema"]["schema"]["properties"]["labels"]
    # OpenAI strict schemas reject uniqueItems ("'uniqueItems' is not permitted"), so the
    # parser collapses repeats instead.
    assert labels["type"] == "array" and "uniqueItems" not in labels
    assert parse_chat_response("unfair_tos", make_body('{"labels": []}'), 0.5) == ([], {})


def make_body(content, model=MODEL, **extra):
    message = {"role": "assistant", "content": content}
    message.update(extra)
    return {"model": model, "choices": [{"message": message}]}


@pytest.mark.parametrize(
    "body,reason",
    [
        (make_body("not json"), "non-JSON content"),
        (make_body('{"label": 100}'), "label out of range"),
        (make_body('{"label": [0, 1]}'), "two labels for a single-label task"),
        (make_body('{"labels": [0]}'), "wrong key"),
        (make_body(""), "empty content"),
        (make_body("{}", refusal="cannot help"), "refusal"),
        ({"model": MODEL, "choices": []}, "no choices"),
        ({"choices": [{"message": {"content": '{"label": 0}'}}]}, "missing model id"),
    ],
)
def test_malformed_answers_raise_instead_of_defaulting(body, reason):
    with pytest.raises(ValueError):
        parse_chat_response("ledgar", body, 0.5)


def test_duplicate_multilabel_answers_are_collapsed():
    assert parse_chat_response("unfair_tos", make_body('{"labels": [1, 1]}'), 0.5) == ([1], {})


def test_chat_run_uses_chat_endpoint_and_scores_all_tasks(prepared, tmp_path):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=fake_chat_response(request))

    result = asyncio.run(
        run_benchmark(
            prepared,
            tmp_path / "out",
            model=MODEL,
            endpoint=DEFAULT_ENDPOINT,
            api_key="test-secret",
            protocol="chat",
            transport=httpx.MockTransport(handler),
        )
    )
    assert set(seen) == {CHAT_ENDPOINT}
    assert result["complete"] and result["resolved_models"] == [MODEL]
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert manifest["config"]["protocol"] == "chat"
    records = read_jsonl(tmp_path / "out" / "predictions.jsonl")
    assert {r["status"] for r in records} == {"ok"}
    assert all(r["probabilities"] == {} for r in records)
    usage = result["usage"]
    assert usage["input_tokens"] == 100 * len(records)
    assert usage["output_tokens"] == 5 * len(records)


def test_chat_refusal_is_checkpointed_as_an_error_not_a_prediction(prepared, tmp_path):
    def handler(request):
        body = fake_chat_response(request)
        body["choices"][0]["message"] = {"role": "assistant", "refusal": "no"}
        return httpx.Response(200, json=body)

    result = asyncio.run(
        run_benchmark(
            prepared,
            tmp_path / "out",
            model=MODEL,
            endpoint=DEFAULT_ENDPOINT,
            api_key="test-secret",
            protocol="chat",
            transport=httpx.MockTransport(handler),
        )
    )
    assert not result["complete"]
    records = read_jsonl(tmp_path / "out" / "predictions.jsonl")
    assert records and all(r["status"] == "error" for r in records)
    assert all("prediction" not in r for r in records)
