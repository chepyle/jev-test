import json

import pytest

from jev_test.data import load_prepared, normalize, sample_indices
from jev_test.questions import build_request, parse_response, truncate
from jev_test.tasks import get_task


def test_gold_labels_and_unrelated_fields_never_enter_requests(prepared):
    _, rows = load_prepared(prepared)
    for row in rows:
        original, _ = build_request(row, "jev", 48_000)
        modified, _ = build_request(
            {**row, "gold": [4], "label": 999, "labels": [999], "secret": "DO NOT LEAK"},
            "jev",
            48_000,
        )
        assert original == modified
        assert "DO NOT LEAK" not in json.dumps(original)


def test_casehold_preserves_all_endings_when_context_truncated():
    row = normalize(
        "case_hold",
        0,
        {
            "context": "START " + "x" * 1000 + " END",
            "endings": [str(i) * 500 for i in range(5)],
            "label": 2,
        },
    )
    request, info = build_request(row, "jev", 100)
    assert info["truncated"]
    assert len(request["state"]["document"]) == 100
    assert request["state"]["document"].startswith("START ")
    assert request["state"]["document"].endswith(" END")
    assert list(request["questions"]["label"]["criteria"].values()) == row["endings"]


def test_semantic_labels_and_zero_based_indices():
    assert get_task("eurlex").codes[0] == "100163"
    assert get_task("eurlex").descriptions[0] == "political framework"
    assert len(get_task("scotus").codes) == 13
    assert get_task("scotus").descriptions[0] == "Criminal Procedure"
    assert "Article 2:" in get_task("ecthr_a").descriptions[0]


def test_multilabel_threshold_is_strictly_greater_than():
    response = {
        "model": "jev",
        "answers": {
            f"label_{i}": {"type": "noul", "noul": 0.5 if i == 0 else 0.51} for i in range(8)
        },
    }
    predictions, _ = parse_response("unfair_tos", response, 0.5)
    assert predictions == list(range(1, 8))


@pytest.mark.parametrize("value", [True, "0.9", -0.1, 1.1, float("nan"), float("inf"), None])
def test_malformed_probabilities_are_failures(value):
    response = {
        "model": "jev",
        "answers": {f"label_{i}": {"type": "noul", "noul": value} for i in range(8)},
    }
    with pytest.raises(ValueError):
        parse_response("unfair_tos", response, 0.5)


def test_missing_answers_are_not_treated_as_negative_labels():
    with pytest.raises(ValueError, match="missing"):
        parse_response("eurlex", {"model": "jev", "answers": {}}, 0.5)


@pytest.mark.parametrize("choice", [True, 0, "13", "Criminal Procedure", [], {}])
def test_invalid_choices_are_failures(choice):
    with pytest.raises(ValueError):
        parse_response(
            "scotus",
            {"model": "jev", "answers": {"label": {"type": "choice", "choice": choice}}},
            0.5,
        )


def test_sampling_and_unlimited_input():
    assert sample_indices(100, 10, 42) == sample_indices(100, 10, 42)
    assert sample_indices(100, 10, 42) != list(range(10))
    assert sample_indices(10, 0, 42) == list(range(10))
    assert sample_indices(10, 100, 42) == list(range(10))
    text = "x" * 100_000
    assert truncate(text, 0) == (text, False)


def test_modified_prepared_data_is_rejected(prepared):
    with (prepared / "scotus.jsonl").open("a") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError, match="Data changed"):
        load_prepared(prepared)
