"""Cross-check our intent-suite macro-F1 against the community Decision Index v0.2.1.

    uv run python analysis/decision_index_check.py > analysis/decision-index-check.json

The index scores the same test sets (BANKING77 3,080, CLINC150+OOS 5,500) with its own
harness and prompts. Its numbers are copied from `data/index-v0.2.1.json` of the HF Space
`multimodalart/jev-decision-index` at revision cdbd1cab (generated 2026-09-28); Cloudflare's
Clef post (2026-10-01) reuses them for its Jev, Kev 9B and Laya columns. Our side is
recomputed from the prediction ledgers with a 1000-resample percentile bootstrap, seed 0.
"""

import json
from pathlib import Path

import numpy as np
from sklearn.metrics import f1_score

from jev_test.analysis import interval, load_source

RESAMPLES = 1000
LEDGERS = {
    "jev": "results/jev-intents-test/predictions.jsonl",
    "kev-4b": "results/kev4b-intents-test/predictions.jsonl",
    "llm2jev": "results/llm2jev-intents-test/predictions.jsonl",
}
# Decision Index v0.2.1 macro-F1; null where the index has no entry for that model.
INDEX = {
    "jev": {"banking77": 0.7974, "clinc150": 0.8927},
    "kev-4b": {"banking77": 0.8224, "clinc150": 0.7936},
    "llm2jev": {"banking77": None, "clinc150": None},
}


def macro_f1(gold: np.ndarray, pred: np.ndarray) -> float:
    labels = np.union1d(gold, pred)
    return float(f1_score(gold, pred, labels=labels, average="macro", zero_division=0))


def main(seed: int = 0) -> dict:
    out = {"resamples": RESAMPLES, "seed": seed, "sources": {}}
    for name, path in LEDGERS.items():
        tasks = load_source(Path(path))
        out["sources"][name] = {}
        for task in ("banking77", "clinc150"):
            records = [tasks[task][i] for i in sorted(tasks[task])]
            gold = np.array([r["gold"][0] for r in records])
            pred = np.array([r["prediction"][0] for r in records])
            rng = np.random.default_rng(seed)
            samples = []
            for _ in range(RESAMPLES):
                idx = rng.integers(0, len(gold), len(gold))
                samples.append(macro_f1(gold[idx], pred[idx]))
            ours = macro_f1(gold, pred)
            index = INDEX[name][task]
            out["sources"][name][task] = {
                "n": len(gold),
                "macro_f1": ours,
                "macro_f1_ci95": interval(samples),
                "index_macro_f1": index,
                "ours_minus_index": None if index is None else ours - index,
            }
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
