import pytest

from jev_test.decisions import build_decisions_request, parse_decisions_response


def response(answers):
    return {"model": "gpt-6-luna", "answers": answers}


def test_multilabel_refusal_is_imputed_not_applied():
    answers = [{"type": "predicate", "name": f"label_{i}", "probability": 0.9} for i in range(8)]
    answers[1] = {"type": "refusal", "name": "label_1"}
    labels, probs = parse_decisions_response("unfair_tos", response(answers), 0.5)
    assert 1 not in labels and probs["1"] == 0.0 and labels == [0, 2, 3, 4, 5, 6, 7]


def test_choice_refusal_is_error():
    from jev_test.decisions import Refusal

    with pytest.raises(Refusal):
        parse_decisions_response("ledgar", response([{"type": "refusal", "name": "label"}]), 0.5)


def test_choice_probabilities_normalized_to_dict():
    task_codes = 100
    probs = [{"value": str(i), "probability": 1.0 if i == 7 else 0.0} for i in range(task_codes)]
    answer = {"type": "choice", "name": "label", "choice": "7", "probabilities": probs}
    labels, p = parse_decisions_response("ledgar", response([answer]), 0.5)
    assert labels == [7] and p["7"] == 1.0 and len(p) == 100


def test_request_has_no_gold_and_valid_shape():
    row = {"task": "unfair_tos", "text": "x", "gold": [1], "id": "a", "index": 0}
    payload, _ = build_decisions_request(row, "gpt-6-luna", 48_000)
    assert set(payload) == {"model", "input", "questions"} and "gold" not in str(payload)
    assert all(q["type"] == "predicate" for q in payload["questions"])
