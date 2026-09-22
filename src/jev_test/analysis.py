"""Detailed agreement, calibration, and paired-comparison metrics beyond micro/macro-F1.

A *source* is any JSONL of per-example records with ``id``, ``task``, ``gold``, ``prediction``,
and (optionally) ``probabilities``: the Jev ledger, or predictions exported from a fine-tuned
baseline. Records with ``status`` other than ``ok`` are skipped. Single-source metrics compare
a model to gold; paired metrics compare two sources on the examples both scored.
"""

import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import (
    average_precision_score,
    cohen_kappa_score,
    f1_score,
    matthews_corrcoef,
    roc_auc_score,
)

from jev_test.metrics import score
from jev_test.storage import read_jsonl
from jev_test.tasks import get_task

BOOTSTRAP = 1000
ECE_BINS = 10


def load_source(path: Path) -> dict[str, dict[str, dict]]:
    """Return {task: {id: record}}, keeping the last ok record per id."""
    by_task: dict[str, dict[str, dict]] = {}
    for record in read_jsonl(path):
        if record.get("status", "ok") != "ok":
            continue
        by_task.setdefault(record["task"], {})[record["id"]] = record
    return by_task


def indicator(rows: list[list[int]], width: int) -> np.ndarray:
    matrix = np.zeros((len(rows), width), dtype=int)
    for index, labels in enumerate(rows):
        matrix[index, labels] = 1
    return matrix


def probability_matrix(records: list[dict], width: int) -> np.ndarray | None:
    if any(not record.get("probabilities") for record in records):
        return None
    matrix = np.zeros((len(records), width))
    for index, record in enumerate(records):
        for label, value in record["probabilities"].items():
            matrix[index, int(label)] = value
    return matrix


def ece(confidence: np.ndarray, correct: np.ndarray, bins: int = ECE_BINS) -> float:
    """Expected calibration error with equal-width bins over [0, 1]."""
    edges = np.minimum((confidence * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        mask = edges == b
        if mask.any():
            total += mask.mean() * abs(confidence[mask].mean() - correct[mask].mean())
    return float(total)


def interval(values: list[float]) -> list[float]:
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def single_label_metrics(gold: np.ndarray, pred: np.ndarray, probs: np.ndarray | None) -> dict:
    labels = np.union1d(gold, pred)
    result = {
        "accuracy": float((gold == pred).mean()),
        "cohen_kappa": float(cohen_kappa_score(gold, pred)),
        "mcc": float(matthews_corrcoef(gold, pred)),
        "macro_f1": float(f1_score(gold, pred, labels=labels, average="macro", zero_division=0)),
    }
    if probs is not None:
        rows = np.arange(len(gold))
        order = np.argsort(-probs, axis=1)
        result["top3_accuracy"] = float((order[:, :3] == gold[:, None]).any(axis=1).mean())
        onehot = np.zeros_like(probs)
        onehot[rows, gold] = 1
        result["brier"] = float(((probs - onehot) ** 2).sum(axis=1).mean())
        result["ece"] = ece(probs[rows, pred], (gold == pred).astype(float))
        result["mean_confidence"] = float(probs[rows, pred].mean())
    return result


def column_kappas(truth: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    """Cohen's kappa per binary label column; NaN where kappa is undefined (p_e == 1)."""
    n = truth.shape[0]
    t1, p1 = truth.mean(axis=0), predicted.mean(axis=0)
    observed = (truth == predicted).sum(axis=0) / n
    expected = t1 * p1 + (1 - t1) * (1 - p1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(expected < 1, (observed - expected) / (1 - expected), np.nan)


def multilabel_metrics(truth: np.ndarray, predicted: np.ndarray, probs: np.ndarray | None) -> dict:
    """Metrics over the task's real label columns (no synthetic none-of-the-above column)."""
    kappas = column_kappas(truth, predicted)
    kappas = kappas[~np.isnan(kappas)]
    tp = int((truth & predicted).sum())
    result = {
        "pooled_kappa": float(cohen_kappa_score(truth.ravel(), predicted.ravel())),
        "macro_label_kappa": float(kappas.mean()) if kappas.size else 0.0,
        "labels_with_kappa": len(kappas),
        "micro_precision": tp / max(1, int(predicted.sum())),
        "micro_recall": tp / max(1, int(truth.sum())),
        "samples_f1": float(f1_score(truth, predicted, average="samples", zero_division=1)),
        "exact_match": float((truth == predicted).all(axis=1).mean()),
        "mean_gold_labels": float(truth.sum(axis=1).mean()),
        "mean_predicted_labels": float(predicted.sum(axis=1).mean()),
    }
    if probs is not None:
        scorable = truth.any(axis=0) & ~truth.all(axis=0)
        result["macro_roc_auc"] = float(
            roc_auc_score(truth[:, scorable], probs[:, scorable], average="macro")
        )
        result["micro_average_precision"] = float(
            average_precision_score(truth.ravel(), probs.ravel())
        )
        result["brier"] = float(((probs - truth) ** 2).mean())
        result["ece"] = ece(probs.ravel(), truth.ravel().astype(float))
    return result


def oracle_threshold(task_name: str, gold: list, probs: np.ndarray) -> dict:
    """Best single global threshold on the scored split. Diagnostic upper bound only:
    choosing it on test data is test-set tuning and must not be reported as a result."""
    best = {"threshold": 0.5, "micro_f1": -1.0, "macro_f1": 0.0}
    for threshold in np.round(np.arange(0.05, 0.96, 0.05), 2):
        rows = [np.flatnonzero(p > threshold).tolist() for p in probs]
        s = score(task_name, gold, rows)
        if s["micro_f1"] > best["micro_f1"]:
            best = {
                "threshold": float(threshold),
                "micro_f1": s["micro_f1"],
                "macro_f1": s["macro_f1"],
            }
    return best


def breakdown(task_name: str, records: list[dict]) -> dict:
    """Micro-F1 by truncation status and by original-length quartile."""
    out = {}
    lengths = np.array([r.get("input", {}).get("original_chars", 0) for r in records])
    groups = {
        "truncated": [r for r in records if r.get("input", {}).get("truncated")],
        "not_truncated": [r for r in records if not r.get("input", {}).get("truncated")],
    }
    if lengths.any():
        cuts = np.percentile(lengths, [25, 50, 75])
        quartile = np.searchsorted(cuts, lengths, side="right")
        for q in range(4):
            groups[f"length_q{q + 1}"] = [
                r for r, k in zip(records, quartile, strict=True) if k == q
            ]
    for name, group in groups.items():
        if group:
            s = score(task_name, [r["gold"] for r in group], [r["prediction"] for r in group])
            out[name] = {"n": len(group), "micro_f1": s["micro_f1"]}
    return out


def analyze_task(task_name: str, records: list[dict], rng: np.random.Generator) -> dict:
    task = get_task(task_name)
    gold = [r["gold"] for r in records]
    pred = [r["prediction"] for r in records]
    width = len(task.codes)
    probs = probability_matrix(records, width)
    if task.multilabel:
        truth, predicted = indicator(gold, width), indicator(pred, width)
        point = multilabel_metrics(truth, predicted, probs)
        key = "macro_label_kappa"

        def kappa(idx):
            k = column_kappas(truth[idx], predicted[idx])
            return float(np.nanmean(k)) if (~np.isnan(k)).any() else 0.0
    else:
        g, p = np.array([x[0] for x in gold]), np.array([x[0] for x in pred])
        point = single_label_metrics(g, p, probs)
        key = "cohen_kappa"

        def kappa(idx):
            return float(cohen_kappa_score(g[idx], p[idx]))

    point.update(score(task_name, gold, pred))
    samples = {key: [], "micro_f1": []}
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, len(records), len(records))
        samples[key].append(kappa(idx))
        samples["micro_f1"].append(
            score(task_name, [gold[i] for i in idx], [pred[i] for i in idx])["micro_f1"]
        )
    result = {
        "n": len(records),
        "metrics": point,
        "ci95": {k: interval(v) for k, v in samples.items()},
        "breakdown": breakdown(task_name, records),
    }
    if task.multilabel and probs is not None:
        result["oracle_threshold_diagnostic"] = oracle_threshold(task_name, gold, probs)
    return result


def paired(task_name: str, a: list[dict], b: list[dict], rng: np.random.Generator) -> dict:
    """Compare two sources on the same examples (records aligned by position)."""
    task = get_task(task_name)
    gold = [r["gold"] for r in a]
    pa, pb = [r["prediction"] for r in a], [r["prediction"] for r in b]
    if task.multilabel:
        width = len(task.codes)
        xa, xb = indicator(pa, width), indicator(pb, width)
        agreement = {
            "inter_model_pooled_kappa": float(cohen_kappa_score(xa.ravel(), xb.ravel())),
            "identical_label_sets": float((xa == xb).all(axis=1).mean()),
        }
        correct_a = np.array([sorted(x) == sorted(y) for x, y in zip(pa, gold, strict=True)])
        correct_b = np.array([sorted(x) == sorted(y) for x, y in zip(pb, gold, strict=True)])
    else:
        ga = np.array([x[0] for x in gold])
        la, lb = np.array([x[0] for x in pa]), np.array([x[0] for x in pb])
        agreement = {
            "inter_model_kappa": float(cohen_kappa_score(la, lb)),
            "same_prediction": float((la == lb).mean()),
        }
        correct_a, correct_b = la == ga, lb == ga
    only_a = int((correct_a & ~correct_b).sum())
    only_b = int((~correct_a & correct_b).sum())
    mcnemar = binomtest(only_a, only_a + only_b, 0.5).pvalue if only_a + only_b else 1.0
    diffs = {"micro_f1": [], "macro_f1": []}
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, len(a), len(a))
        g = [gold[i] for i in idx]
        sa, sb = (
            score(task_name, g, [pa[i] for i in idx]),
            score(task_name, g, [pb[i] for i in idx]),
        )
        for k in diffs:
            diffs[k].append(sa[k] - sb[k])
    full_a, full_b = score(task_name, gold, pa), score(task_name, gold, pb)
    return {
        "n": len(a),
        **agreement,
        "exact_correct_only_a": only_a,
        "exact_correct_only_b": only_b,
        "both_exact_correct": int((correct_a & correct_b).sum()),
        "neither_exact_correct": int((~correct_a & ~correct_b).sum()),
        "mcnemar_exact_p": float(mcnemar),
        "delta_micro_f1": full_a["micro_f1"] - full_b["micro_f1"],
        "delta_micro_f1_ci95": interval(diffs["micro_f1"]),
        "delta_macro_f1": full_a["macro_f1"] - full_b["macro_f1"],
        "delta_macro_f1_ci95": interval(diffs["macro_f1"]),
    }


def analyze(sources: dict[str, Path], seed: int = 0) -> dict:
    """Analyze each named source; add paired comparisons of the first against the rest."""
    loaded = {name: load_source(path) for name, path in sources.items()}
    names = list(loaded)
    report: dict = {"bootstrap": BOOTSTRAP, "seed": seed, "sources": {}, "paired": {}}
    for name in names:
        rng = np.random.default_rng(seed)
        report["sources"][name] = {
            task: analyze_task(task, list(recs.values()), rng)
            for task, recs in loaded[name].items()
        }
    for other in names[1:]:
        key = f"{names[0]}_vs_{other}"
        report["paired"][key] = {}
        for task, recs in loaded[names[0]].items():
            shared = sorted(set(recs) & set(loaded[other].get(task, {})))
            if not shared:
                continue
            rng = np.random.default_rng(seed)
            report["paired"][key][task] = paired(
                task, [recs[i] for i in shared], [loaded[other][task][i] for i in shared], rng
            )
    return report


def write_analysis(sources: dict[str, Path], output: Path, seed: int = 0) -> dict:
    report = analyze(sources, seed)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report
