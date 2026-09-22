"""Paired bootstrap of macro ROC-AUC differences between two sources on multi-label tasks.

    uv run python analysis/paired_auc.py results/full-test/predictions.jsonl \
        results/bert-seed1/predictions.jsonl > analysis/paired-auc.json

ROC-AUC is threshold-free, so it separates label ranking from the 0.5 cut-off. Resamples
examples; a label column is scored only if the resample has both positives and negatives.
"""

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from jev_test.analysis import indicator, interval, load_source, probability_matrix
from jev_test.tasks import get_task

RESAMPLES = 1000


def macro_auc(truth: np.ndarray, probs: np.ndarray) -> float:
    scorable = truth.any(axis=0) & ~truth.all(axis=0)
    return float(roc_auc_score(truth[:, scorable], probs[:, scorable], average="macro"))


def main(path_a: Path, path_b: Path, seed: int = 0) -> dict:
    a, b = load_source(path_a), load_source(path_b)
    out = {"resamples": RESAMPLES, "seed": seed, "tasks": {}}
    for name, records in a.items():
        task = get_task(name)
        if not task.multilabel or name not in b:
            continue
        ids = sorted(set(records) & set(b[name]))
        truth = indicator([records[i]["gold"] for i in ids], len(task.codes))
        pa = probability_matrix([records[i] for i in ids], len(task.codes))
        pb = probability_matrix([b[name][i] for i in ids], len(task.codes))
        rng = np.random.default_rng(seed)
        diffs = []
        for _ in range(RESAMPLES):
            idx = rng.integers(0, len(ids), len(ids))
            diffs.append(macro_auc(truth[idx], pa[idx]) - macro_auc(truth[idx], pb[idx]))
        out["tasks"][name] = {
            "n": len(ids),
            "macro_auc_a": macro_auc(truth, pa),
            "macro_auc_b": macro_auc(truth, pb),
            "delta": macro_auc(truth, pa) - macro_auc(truth, pb),
            "delta_ci95": interval(diffs),
        }
    return out


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
