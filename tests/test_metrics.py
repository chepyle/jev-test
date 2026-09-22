import pytest

from jev_test.metrics import aggregate, score


@pytest.mark.parametrize("task,width", [("ecthr_a", 11), ("ecthr_b", 11), ("unfair_tos", 9)])
def test_empty_labels_are_a_scored_none_class(task, width):
    scores = score(task, [[], [0]], [[], []])
    assert scores["micro_f1"] == pytest.approx(0.5)
    assert scores["macro_f1"] == pytest.approx((2 / 3) / width)
    assert scores["exact_match"] == 0.5


def test_eurlex_has_no_synthetic_none_class():
    scores = score("eurlex", [[], [0]], [[], []])
    assert scores["micro_f1"] == 0
    assert scores["macro_f1"] == 0
    assert scores["exact_match"] == 0.5


@pytest.mark.parametrize("task", ["scotus", "ledgar", "case_hold"])
def test_multiclass_micro_macro_follow_upstream_observed_classes(task):
    scores = score(task, [[0], [0], [1]], [[0], [1], [1]])
    assert scores["micro_f1"] == pytest.approx(2 / 3)
    assert scores["macro_f1"] == pytest.approx(2 / 3)
    assert scores["exact_match"] == pytest.approx(2 / 3)


def test_casehold_macro_is_not_forced_to_equal_accuracy():
    scores = score("case_hold", [[0], [0], [0], [1]], [[0], [0], [0], [0]])
    assert scores["micro_f1"] == 0.75
    assert scores["macro_f1"] == pytest.approx(3 / 7)


def test_aggregation_handles_zero_without_log_or_division_errors():
    combined = aggregate([{"micro_f1": 0.0, "macro_f1": 0.0}, {"micro_f1": 1.0, "macro_f1": 0.5}])
    assert combined["micro_f1"] == {"arithmetic": 0.5, "geometric": 0, "harmonic": 0}
    assert combined["macro_f1"]["arithmetic"] == 0.25


def test_invalid_predictions_cannot_be_silently_scored():
    with pytest.raises(ValueError):
        score("scotus", [[0]], [[13]])
    with pytest.raises(ValueError):
        score("ledgar", [[0]], [[]])
