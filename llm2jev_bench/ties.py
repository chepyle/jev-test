"""Count multi-label noul answers of exactly 0.5 in a prediction ledger.

LLM2Jev scores a noul question with true/false criteria as two yes/no prompts and
L1-normalizes the pair. When the model says "yes" to both with probability ~1 (or ~0), the
pair normalizes to exactly 0.5, which the strict `> threshold` rule reads as "does not apply".

    uv run python llm2jev_bench/ties.py results/llm2jev-full/predictions.jsonl
"""

import json
import sys
from collections import Counter
from pathlib import Path

from jev_test.analysis import load_source
from jev_test.tasks import get_task


def main(path: Path) -> dict:
    out = {}
    for task, records in load_source(path).items():
        if not get_task(task).multilabel:
            continue
        counts = Counter()
        for r in records.values():
            for label, p in r["probabilities"].items():
                counts["decisions"] += 1
                if p == 0.5:
                    counts["ties"] += 1
                    counts["ties_gold_positive"] += int(label) in r["gold"]
        out[task] = {**counts, "tie_rate": counts["ties"] / counts["decisions"]}
    return out


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=2))
