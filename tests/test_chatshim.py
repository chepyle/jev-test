import json

import pytest

from jev_test.chatshim import Shim, build_chat_request, render, to_system_one

REQUEST = {
    "state": {"policy": "Late reports are refused.", "case": "Filed on time."},
    "questions": {
        "topic": {
            "type": "choice",
            "instructions": "Topic?",
            "criteria": {"world": "World news", "business": None},
        },
        "late": {"type": "noul", "instructions": "Is it late?"},
        "decision": {
            "type": "score",
            "instructions": "How late?",
            "criteria": ["On time", "Late", "Refused"],
        },
    },
}


def chat_body(answer):
    return {
        "model": "openai/test",
        "choices": [{"message": {"content": json.dumps(answer)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "cost": 0.001},
    }


def test_render_matches_kev_labels():
    assert render({"a": "x", "b": {"c": 1}}) == "a: x\nb:\n  c: 1"


def test_schema_has_one_typed_property_per_question():
    payload = build_chat_request(REQUEST, "m")
    schema = payload["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["topic", "late", "decision"]
    assert schema["properties"]["topic"] == {"type": "string", "enum": ["world", "business"]}
    assert schema["properties"]["late"] == {"type": "boolean"}
    assert schema["properties"]["decision"] == {"type": "integer", "enum": [0, 1, 2]}
    user = payload["messages"][1]["content"]
    assert "policy: Late reports are refused." in user and "- business\n" in user


def test_answers_are_one_hot_in_kev_keys():
    out = to_system_one(REQUEST, chat_body({"topic": "business", "late": False, "decision": 2}))
    assert out["answers"]["topic"]["probabilities"] == {"world": 0.0, "business": 1.0}
    assert out["answers"]["late"] == {"type": "noul", "noul": 0.0}
    assert out["answers"]["decision"]["probabilities"] == {"0": 0.0, "1": 0.0, "2": 1.0}
    assert out["usage"] == {"input_tokens": 10, "output_tokens": 3}


@pytest.mark.parametrize(
    "answer",
    [
        {"topic": "sports", "late": True, "decision": 0},
        {"topic": "world", "late": "yes", "decision": 0},
    ],
)
def test_malformed_answers_raise(answer):
    with pytest.raises(ValueError):
        to_system_one(REQUEST, chat_body(answer))


def test_cached_answer_is_replayed_without_a_call(tmp_path):
    shim = Shim("m", tmp_path, "key")
    calls = []
    shim.http.post = lambda *a, **k: (
        calls.append(1)
        or type(
            "R",
            (),
            {
                "status_code": 200,
                "json": lambda self: chat_body({"topic": "world", "late": True, "decision": 1}),
            },
        )()
    )
    first = shim.answer(REQUEST)
    assert shim.answer({**REQUEST, "model": "ignored"}) == first
    assert len(calls) == 1
