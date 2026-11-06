"""Holm adjustment of every paired full-test comparison, for the micro-F1 differences reported.

    uv run python analysis/multiplicity.py > analysis/multiplicity.json

Every interval and p-value in analysis/*.json is per comparison, uncorrected. This collects
each distinct (model A ledger, model B ledger, task) comparison from the paired sections of
the files listed in scripts/regenerate_analysis.sh (the 50-per-task smoke comparison is left
out; duplicates such as Jev vs BERT in both jev-vs-bert.json and three-way.json count once),
and applies Holm's step-down correction at family-wise 0.05 to two p-values:

- `p_boot`, primary: a two-sided normal approximation from the comparison's own paired
  bootstrap of the micro-F1 difference (standard error = 95% interval width / 3.92). It tests
  the statistic the text reports, on every task.
- `mcnemar_exact_p`, secondary: exact McNemar on exact-match correctness. On single-label
  tasks that is accuracy (= micro-F1); on multi-label tasks it is label-set exact match, which
  is rare on EUR-LEX, so it is reported but not used there.

A percentile interval at the family-wise level (2.5/m percentiles for m comparisons) is not
estimable from 1,000 resamples, hence the normal approximation.
"""

import json
import math
import re
from pathlib import Path

from jev_test.tasks import get_task

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = {"sample50-jev-vs-luna.json"}


def comparisons() -> dict:
    jobs = (ROOT / "scripts" / "regenerate_analysis.sh").read_text()
    found = {}
    for output, spec in re.findall(r"^analyze (\S+) (.+)$", jobs, re.M):
        if output in EXCLUDE:
            continue
        runs = dict(s.split("=") for s in spec.split())
        names = list(runs)
        paired = json.loads((ROOT / "analysis" / output).read_text())["paired"]
        for other in names[1:]:
            for task, result in paired[f"{names[0]}_vs_{other}"].items():
                key = (runs[names[0]], runs[other], task)
                found.setdefault(
                    key,
                    {
                        "a": names[0],
                        "b": other,
                        "a_run": runs[names[0]],
                        "b_run": runs[other],
                        "task": task,
                        "file": output,
                        "n": result["n"],
                        "delta_micro_f1": result["delta_micro_f1"],
                        "delta_micro_f1_ci95": result["delta_micro_f1_ci95"],
                        "mcnemar_exact_p": result["mcnemar_exact_p"],
                    },
                )
    return found


def p_boot(delta: float, ci: list[float]) -> float:
    se = (ci[1] - ci[0]) / 3.92
    return math.erfc(abs(delta) / se / math.sqrt(2)) if se > 0 else float(delta == 0)


def holm(rows: list[dict], key: str, alpha: float = 0.05) -> None:
    order = sorted(range(len(rows)), key=lambda i: rows[i][key])
    m, running, rejecting = len(rows), 0.0, True
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * rows[i][key]))  # monotone step-down
        rejecting = rejecting and running < alpha
        rows[i][f"holm_{key}"] = running
        rows[i][f"holm_{key}_reject"] = rejecting


def main() -> dict:
    rows = sorted(comparisons().values(), key=lambda r: (r["file"], r["b"], r["task"]))
    for row in rows:
        lo, hi = row["delta_micro_f1_ci95"]
        row["ci_excludes_zero"] = lo > 0 or hi < 0
        row["multilabel"] = get_task(row["task"]).multilabel
        row["p_boot"] = p_boot(row["delta_micro_f1"], row["delta_micro_f1_ci95"])
    holm(rows, "p_boot")
    single = [r for r in rows if not r["multilabel"]]
    holm(single, "mcnemar_exact_p")
    lost = [r for r in rows if r["ci_excludes_zero"] and not r["holm_p_boot_reject"]]
    keys = ("file", "a", "b", "task", "delta_micro_f1", "delta_micro_f1_ci95", "holm_p_boot")
    return {
        "family_size": len(rows),
        "alpha": 0.05,
        "ci_excludes_zero": sum(r["ci_excludes_zero"] for r in rows),
        "holm_p_boot_rejects": sum(r["holm_p_boot_reject"] for r in rows),
        "single_label_family_size": len(single),
        "holm_mcnemar_rejects_single_label": sum(r["holm_mcnemar_exact_p_reject"] for r in single),
        "ci_excludes_zero_but_not_holm": [{k: r[k] for k in keys} for r in lost],
        "comparisons": rows,
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
