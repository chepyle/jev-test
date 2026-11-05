"""UNFAIR-ToS sensitivity of the Decisions-API run to refused-label imputation.

Refused predicates are scored as "label not applied". This drops every UNFAIR-ToS document
with at least one refusal and re-scores Decisions, Jev and chat Luna, with a paired bootstrap
(1,000 resamples, seed 0) of Decisions minus Jev micro-F1.

    uv run python analysis/decisions_unfair_sensitivity.py
"""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

from jev_test.metrics import score

ROOT = Path(__file__).resolve().parent.parent


def load(path: str) -> dict:
    out = {}
    for line in (ROOT / path).open():
        r = json.loads(line)
        if r["status"] == "ok":
            out[r["id"]] = r
    return out


D = load("results/decisions-full/predictions.jsonl")
J = load("results/full-test/predictions.jsonl")
L = load("results/luna-full/predictions.jsonl")
ids = [i for i in D if D[i]["task"] == "unfair_tos"]
refused = {i for i in ids if any(a["type"] == "refusal" for a in D[i]["response"]["answers"])}
keep = [i for i in ids if i not in refused]
out = {"n_all": len(ids), "n_refused_rows": len(refused), "n_kept": len(keep)}
for name, src in (("decisions", D), ("jev", J), ("luna_chat", L)):
    for label, subset in (("all", ids), ("kept", keep)):
        s = score(
            "unfair_tos", [src[i]["gold"] for i in subset], [src[i]["prediction"] for i in subset]
        )
        out[f"{name}_{label}_micro_f1"] = round(s["micro_f1"], 4)


def matrix(rows: list[list[int]]) -> np.ndarray:
    m = np.zeros((len(rows), 9), int)
    for k, labels in enumerate(rows):
        m[k, labels] = 1
        if not labels:
            m[k, -1] = 1
    return m


gold, a, b = (
    matrix([src[i][key] for i in keep])
    for src, key in ((D, "gold"), (D, "prediction"), (J, "prediction"))
)
rng = np.random.default_rng(0)
deltas = []
for _ in range(1000):
    ix = rng.integers(0, len(keep), len(keep))
    deltas.append(
        f1_score(gold[ix], a[ix], average="micro", zero_division=0)
        - f1_score(gold[ix], b[ix], average="micro", zero_division=0)
    )
out["delta_decisions_minus_jev_kept"] = round(float(np.mean(deltas)), 4)
out["delta_ci95"] = [round(float(x), 4) for x in np.percentile(deltas, [2.5, 97.5])]
(ROOT / "analysis" / "decisions-unfair-sensitivity.json").write_text(
    json.dumps(out, indent=2) + "\n"
)
print(json.dumps(out, indent=2))
