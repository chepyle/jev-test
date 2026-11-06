"""Sensitivity of the Decisions-API scores to how refused label answers are handled.

The Decisions parser scores a refused `predicate` as probability 0.0 ("label not applied"),
so the row stays in F1, ROC-AUC, ECE and Brier, while a System One failure removes the row.
Refusals occur on two tasks (UNFAIR-ToS, ECtHR A). For each, this recomputes Jev − Decisions
under three treatments:

- `impute_0`: as reported (refused label probability 0.0);
- `impute_1`: the opposite bound (refused label probability 1.0, so the label is applied);
- `drop_rows`: every document with at least one refusal removed, for both models.

F1 differences use `jev_test.analysis.paired` (records sorted by id, 1,000 resamples, seed 0);
macro ROC-AUC differences use the resampling of `analysis/paired_auc.py`. ECE and Brier are
point estimates (`jev_test.analysis.multilabel_metrics`).

    uv run python analysis/decisions_refusal_sensitivity.py \
        > analysis/decisions-refusal-sensitivity.json
"""

import copy
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paired_auc import macro_auc  # noqa: E402

from jev_test.analysis import (  # noqa: E402
    BOOTSTRAP,
    indicator,
    interval,
    load_source,
    multilabel_metrics,
    paired,
    probability_matrix,
)
from jev_test.tasks import get_task  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TASKS = ("ecthr_a", "unfair_tos")


def refused_labels(record: dict) -> list[int]:
    return [
        int(a["name"].removeprefix("label_"))
        for a in record["response"]["answers"]
        if a.get("type") == "refusal"
    ]


def imputed(record: dict, value: float) -> dict:
    record = copy.deepcopy(record)
    for label in refused_labels(record):
        record["probabilities"][str(label)] = value
    record["prediction"] = sorted(int(k) for k, p in record["probabilities"].items() if p > 0.5)
    return record


def compare(task: str, jev: list[dict], dec: list[dict]) -> dict:
    width = len(get_task(task).codes)
    f1 = paired(task, jev, dec, np.random.default_rng(0))
    truth = indicator([r["gold"] for r in jev], width)
    pj, pd = probability_matrix(jev, width), probability_matrix(dec, width)
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(BOOTSTRAP):
        idx = rng.integers(0, len(jev), len(jev))
        diffs.append(macro_auc(truth[idx], pj[idx]) - macro_auc(truth[idx], pd[idx]))
    mj = multilabel_metrics(truth, indicator([r["prediction"] for r in jev], width), pj)
    md = multilabel_metrics(truth, indicator([r["prediction"] for r in dec], width), pd)
    return {
        "n": len(jev),
        "jev_minus_decisions": {
            "micro_f1": f1["delta_micro_f1"],
            "micro_f1_ci95": f1["delta_micro_f1_ci95"],
            "macro_f1": f1["delta_macro_f1"],
            "macro_f1_ci95": f1["delta_macro_f1_ci95"],
            "macro_roc_auc": macro_auc(truth, pj) - macro_auc(truth, pd),
            "macro_roc_auc_ci95": interval(diffs),
        },
        "decisions": {k: md[k] for k in ("macro_roc_auc", "ece", "brier")},
        "jev": {k: mj[k] for k in ("macro_roc_auc", "ece", "brier")},
    }


def main() -> dict:
    jev = load_source(ROOT / "results/full-test/predictions.jsonl")
    dec = load_source(ROOT / "results/decisions-full/predictions.jsonl")
    out = {"resamples": BOOTSTRAP, "seed": 0, "tasks": {}}
    for task in TASKS:
        ids = sorted(set(jev[task]) & set(dec[task]))
        refused = [i for i in ids if refused_labels(dec[task][i])]
        kept = [i for i in ids if i not in set(refused)]
        out["tasks"][task] = {
            "n_rows": len(ids),
            "n_rows_with_refusal": len(refused),
            "n_refused_answers": sum(len(refused_labels(dec[task][i])) for i in refused),
            "impute_0": compare(task, [jev[task][i] for i in ids], [dec[task][i] for i in ids]),
            "impute_1": compare(
                task, [jev[task][i] for i in ids], [imputed(dec[task][i], 1.0) for i in ids]
            ),
            "drop_rows": compare(task, [jev[task][i] for i in kept], [dec[task][i] for i in kept]),
        }
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
