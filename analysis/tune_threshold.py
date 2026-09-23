"""Choose multi-label thresholds on validation, then apply them once to test.

    uv run python analysis/tune_threshold.py --val results/jev-val-multilabel/predictions.jsonl \
        --test results/full-test/predictions.jsonl --baseline results/bert-seed1/predictions.jsonl \
        > analysis/threshold-tuning.json

Pre-registered before scoring test:
- primary: one global threshold per task, maximizing validation micro-F1 (upstream's
  model-selection metric), grid 0.05 to 0.95 in steps of 0.05, ties to the value nearest 0.5;
- secondary: one threshold per label maximizing that label's validation F1 (more parameters,
  more risk of overfitting the 1,000 to 5,000 validation documents).
Test labels are used only to score the frozen choice. A label with no positive validation
example keeps 0.5.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from jev_test.analysis import indicator, interval, load_source, probability_matrix
from jev_test.metrics import score
from jev_test.tasks import get_task

GRID = np.round(np.arange(0.05, 0.951, 0.05), 2)
RESAMPLES = 1000


def predict(probs: np.ndarray, thresholds: np.ndarray) -> list[list[int]]:
    return [np.flatnonzero(row > thresholds).tolist() for row in probs]


def nearest_half_best(values: dict[float, float]) -> float:
    top = max(values.values())
    return min((t for t, v in values.items() if v == top), key=lambda t: abs(t - 0.5))


def tune(name: str, gold: list, probs: np.ndarray) -> dict:
    width = probs.shape[1]
    by_global = {
        float(t): score(name, gold, predict(probs, np.full(width, t)))["micro_f1"] for t in GRID
    }
    global_t = nearest_half_best(by_global)
    truth = indicator(gold, width)
    per_label = np.full(width, 0.5)
    for j in range(width):
        if not truth[:, j].any():
            continue
        f1 = {}
        for t in GRID:
            pred = probs[:, j] > t
            tp = int((pred & (truth[:, j] == 1)).sum())
            denominator = int(pred.sum()) + int(truth[:, j].sum())
            f1[float(t)] = 2 * tp / denominator if denominator else 0.0
        per_label[j] = nearest_half_best(f1)
    return {"global": global_t, "per_label": per_label.tolist(), "val_micro_by_global": by_global}


def bootstrap_delta(name, gold, a, b, rng) -> dict:
    full_a, full_b = score(name, gold, a), score(name, gold, b)
    diffs = {"micro_f1": [], "macro_f1": []}
    for _ in range(RESAMPLES):
        idx = rng.integers(0, len(gold), len(gold))
        g = [gold[i] for i in idx]
        sa, sb = score(name, g, [a[i] for i in idx]), score(name, g, [b[i] for i in idx])
        for k in diffs:
            diffs[k].append(sa[k] - sb[k])
    return {k: {"delta": full_a[k] - full_b[k], "ci95": interval(v)} for k, v in diffs.items()}


def main(val: Path, test: Path, baseline: Path | None, seed: int = 0) -> dict:
    val_src, test_src = load_source(val), load_source(test)
    base_src = load_source(baseline) if baseline else {}
    out = {"grid": GRID.tolist(), "resamples": RESAMPLES, "seed": seed, "tasks": {}}
    for name in sorted(val_src):
        task = get_task(name)
        if not task.multilabel:
            continue
        width = len(task.codes)
        vrec = list(val_src[name].values())
        choice = tune(name, [r["gold"] for r in vrec], probability_matrix(vrec, width))
        ids = sorted(test_src[name])
        trec = [test_src[name][i] for i in ids]
        gold, probs = [r["gold"] for r in trec], probability_matrix(trec, width)
        variants = {
            "default_0.5": predict(probs, np.full(width, 0.5)),
            "global": predict(probs, np.full(width, choice["global"])),
            "per_label": predict(probs, np.array(choice["per_label"])),
        }
        result = {
            "n_val": len(vrec),
            "n_test": len(ids),
            "chosen": choice,
            "test": {k: score(name, gold, v) for k, v in variants.items()},
        }
        for variant in ("global", "per_label"):
            rng = np.random.default_rng(seed)
            result[f"{variant}_minus_default"] = bootstrap_delta(
                name, gold, variants[variant], variants["default_0.5"], rng
            )
        if name in base_src and set(ids) <= set(base_src[name]):
            b = [base_src[name][i]["prediction"] for i in ids]
            for variant in ("global", "per_label"):
                rng = np.random.default_rng(seed)
                result[f"{variant}_minus_baseline"] = bootstrap_delta(
                    name, gold, variants[variant], b, rng
                )
        out["tasks"][name] = result
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--val", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    print(json.dumps(main(args.val, args.test, args.baseline), indent=2))
