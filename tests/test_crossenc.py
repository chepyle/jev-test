import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "encoder"))

from crossenc import (  # noqa: E402
    api_request,
    label_index,
    option_keys,
    pairs,
    request_key,
    to_answers,
)

RECORD = {
    "state": {"policy": "Late reports are refused.", "case": "Filed on time."},
    "questions": {
        "topic": {
            "type": "choice",
            "instructions": "Topic?",
            "criteria": {"world": "World news", "business": None},
            "label": "business",
            "src": "x",
        },
        "late": {"type": "noul", "instructions": "Is it late?", "label": False},
        "passage": {
            "type": "noul",
            "instructions": "Supported?",
            "criteria": {"true": "yes it is", "false": "no"},
            "label": True,
        },
        "decision": {
            "type": "score",
            "instructions": "How late?",
            "criteria": ["On time", "Late", "Refused"],
            "label": 2,
        },
    },
    "_meta": {"id": "r1"},
}


def test_request_strips_labels_and_metadata():
    request = api_request(RECORD)
    assert "_meta" not in request
    assert all(
        set(q) <= {"type", "instructions", "criteria"} for q in request["questions"].values()
    )


def test_request_key_ignores_model_field():
    request = api_request(RECORD)
    assert request_key(request) == request_key({**request, "model": "anything"})


def test_one_pair_per_option_in_kev_key_order():
    out = {qid: (keys, pp) for qid, _, keys, pp in pairs(api_request(RECORD))}
    assert out["topic"][0] == ["world", "business"]
    assert [b for _, b in out["topic"][1]] == ["Topic?\nworld: World news", "Topic?\nbusiness"]
    assert out["late"][0] == ["false", "true"] and [b for _, b in out["late"][1]] == [
        "Is it late?\nno",
        "Is it late?\nyes",
    ]
    assert [b for _, b in out["passage"][1]] == [
        "Supported?\nfalse: no",
        "Supported?\ntrue: yes it is",
    ]
    assert out["decision"][0] == ["0", "1", "2"]
    assert out["topic"][1][0][0] == "policy: Late reports are refused.\ncase: Filed on time."


def test_labels_index_the_options():
    qs = RECORD["questions"]
    assert [label_index(qs[k]) for k in ("topic", "late", "passage", "decision")] == [1, 0, 1, 2]
    assert option_keys(qs["decision"]) == ["0", "1", "2"]


def test_answers_in_system_one_shape():
    request = api_request(RECORD)
    probs = {
        "topic": [0.2, 0.8],
        "late": [0.7, 0.3],
        "passage": [0.1, 0.9],
        "decision": [0.1, 0.2, 0.7],
    }
    out = to_answers(request, probs, "m")["answers"]
    assert out["topic"] == {
        "type": "choice",
        "choice": "business",
        "probabilities": {"world": 0.2, "business": 0.8},
    }
    assert out["late"] == {"type": "noul", "noul": 0.3}
    assert out["decision"]["choice"] == "2"


def test_bad_label_raises():
    with pytest.raises(ValueError):
        label_index({"type": "choice", "criteria": {"a": None}, "label": "z"})
