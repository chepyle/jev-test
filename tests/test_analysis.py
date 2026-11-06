import json

import numpy as np
import pytest
from sklearn.metrics import cohen_kappa_score

from jev_test import analysis
from jev_test.analysis import analyze, column_kappas, ece


def write_source(path, task, golds, preds, probabilities=None):
    with path.open("w") as fh:
        for index, (gold, pred) in enumerate(zip(golds, preds, strict=True)):
            record = {
                "id": f"{task}/{index}",
                "task": task,
                "status": "ok",
                "gold": gold,
                "prediction": pred,
            }
            if probabilities is not None:
                record["probabilities"] = probabilities[index]
            fh.write(json.dumps(record) + "\n")
    return path


def test_column_kappas_match_sklearn_and_mark_undefined_columns():
    rng = np.random.default_rng(0)
    truth = (rng.random((40, 4)) < 0.3).astype(int)
    predicted = (rng.random((40, 4)) < 0.4).astype(int)
    truth[:, 3] = predicted[:, 3] = 0  # constant in both: kappa undefined
    kappas = column_kappas(truth, predicted)
    for j in range(3):
        assert kappas[j] == pytest.approx(cohen_kappa_score(truth[:, j], predicted[:, j]))
    assert np.isnan(kappas[3])


def test_ece_is_zero_when_confidence_matches_accuracy():
    confidence = np.array([0.25] * 4 + [0.75] * 4)
    correct = np.array([1, 0, 0, 0, 1, 1, 1, 0], dtype=float)
    assert ece(confidence, correct) == pytest.approx(0.0)
    assert ece(np.ones(4), np.zeros(4)) == pytest.approx(1.0)


def test_single_label_source_reports_kappa_and_probability_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "BOOTSTRAP", 20)
    golds = [[0], [1], [2], [0]]
    preds = [[0], [1], [1], [0]]
    probs = [{"0": 0.9, "1": 0.1}, {"1": 0.8, "2": 0.2}, {"1": 0.6, "2": 0.4}, {"0": 1.0}]
    path = write_source(tmp_path / "a.jsonl", "scotus", golds, preds, probs)
    metrics = analyze({"a": path})["sources"]["a"]["scotus"]["metrics"]
    assert metrics["accuracy"] == 0.75
    assert metrics["cohen_kappa"] == pytest.approx(cohen_kappa_score([0, 1, 2, 0], [0, 1, 1, 0]))
    assert metrics["top3_accuracy"] == 1.0


def test_paired_comparison_counts_disagreements(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "BOOTSTRAP", 20)
    golds = [[0], [1], [2], [0], [1]]
    a = write_source(tmp_path / "a.jsonl", "ledgar", golds, [[0], [1], [2], [1], [1]])
    b = write_source(tmp_path / "b.jsonl", "ledgar", golds, [[0], [2], [2], [0], [0]])
    result = analyze({"a": a, "b": b})["paired"]["a_vs_b"]["ledgar"]
    assert result["n"] == 5
    assert result["exact_correct_only_a"] == 2
    assert result["exact_correct_only_b"] == 1
    assert result["both_exact_correct"] == 2
    assert result["same_prediction"] == pytest.approx(2 / 5)
    assert result["delta_micro_f1"] == pytest.approx(0.2)


def test_multilabel_paired_uses_only_shared_examples(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, "BOOTSTRAP", 20)
    golds = [[0], [], [1, 2], [3]]
    a = write_source(tmp_path / "a.jsonl", "unfair_tos", golds, [[0], [], [1], [3]])
    b = write_source(tmp_path / "b.jsonl", "unfair_tos", golds[:3], [[0], [4], [1, 2]])
    result = analyze({"a": a, "b": b})["paired"]["a_vs_b"]["unfair_tos"]
    assert result["n"] == 3
    assert result["exact_correct_only_a"] == 1
    assert result["exact_correct_only_b"] == 1


def test_clinc_out_of_scope_metrics_follow_the_paper():
    from jev_test.analysis import out_of_scope_metrics

    oos = 42
    gold = np.array([1, 2, 3, oos, oos])
    pred = np.array([1, oos, 4, oos, 5])
    metrics = out_of_scope_metrics(gold, pred, oos)
    assert metrics["in_scope_accuracy"] == pytest.approx(1 / 3)  # oos on in-scope counts wrong
    assert metrics["oos_recall"] == pytest.approx(1 / 2)
    assert metrics["oos_precision"] == pytest.approx(1 / 2)


def test_intervals_do_not_depend_on_ledger_line_order(tmp_path, monkeypatch):
    """Ledgers are written in async completion order; intervals must depend only on content."""
    monkeypatch.setattr(analysis, "BOOTSTRAP", 50)
    rng = np.random.default_rng(3)
    rows = []
    for task in ("ledgar", "unfair_tos"):
        for index in range(30):
            if task == "ledgar":
                gold, pred = [int(rng.integers(3))], [int(rng.integers(3))]
            else:
                gold = sorted({int(x) for x in rng.integers(0, 8, rng.integers(0, 3))})
                pred = sorted({int(x) for x in rng.integers(0, 8, rng.integers(0, 3))})
            rows.append(
                {
                    "id": f"{task}/{index}",
                    "task": task,
                    "status": "ok",
                    "gold": gold,
                    "prediction": pred,
                }
            )
    ordered, shuffled = tmp_path / "ordered.jsonl", tmp_path / "shuffled.jsonl"
    ordered.write_text("".join(json.dumps(r) + "\n" for r in rows))
    permuted = [rows[i] for i in rng.permutation(len(rows))]
    shuffled.write_text("".join(json.dumps(r) + "\n" for r in permuted))
    a = analyze({"a": ordered})["sources"]["a"]
    b = analyze({"a": shuffled})["sources"]["a"]
    for task in ("ledgar", "unfair_tos"):
        assert a[task]["ci95"] == b[task]["ci95"]
        assert "macro_f1" in a[task]["ci95"]


@pytest.mark.parametrize(
    "task", ["ecthr_a", "eurlex", "unfair_tos", "scotus", "ledgar", "case_hold", "clinc150"]
)
def test_resample_scorer_equals_score_exactly(task):
    from jev_test.analysis import ResampleScorer
    from jev_test.metrics import score
    from jev_test.tasks import get_task

    t = get_task(task)
    rng = np.random.default_rng(1)
    n, width = 60, len(t.codes)
    if t.multilabel:
        draw = lambda: sorted({int(x) for x in rng.integers(0, width, rng.integers(0, 4))})  # noqa: E731
    else:
        draw = lambda: [int(rng.integers(0, min(width, 6)))]  # noqa: E731
    gold, pred = [draw() for _ in range(n)], [draw() for _ in range(n)]
    scorer = ResampleScorer(task, gold, pred)
    for _ in range(200):
        idx = rng.integers(0, n, n)
        expected = score(task, [gold[i] for i in idx], [pred[i] for i in idx])
        assert scorer(idx) == (expected["micro_f1"], expected["macro_f1"])
