"""Convert upstream BERT test logits into an analysis source aligned with prepared data.

    uv run python bert/export_predictions.py --logits bert/runs --data data/full-test \
        --output results/bert-seed1/predictions.jsonl

Expects <logits>/<task>/test_logits.npy (row order = the pinned test split). Multi-label
tasks apply sigmoid and upstream's 0.5 threshold; single-label tasks take softmax and argmax.

Upstream's SCOTUS head has 14 outputs (label_list = range(14)) but the released data has 13
classes. The unused last column is dropped only if it never wins the argmax, so predictions
are unchanged; probabilities are renormalized over the 13 real classes.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.special import expit, softmax

from jev_test.metrics import score
from jev_test.tasks import TASK_NAMES, get_task


def export(logits_dir: Path, data_dir: Path, output: Path) -> dict:
    manifest = json.loads((data_dir / "manifest.json").read_text())
    summary = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as out:
        for name in TASK_NAMES:
            path = logits_dir / name / "test_logits.npy"
            if not path.exists():
                continue
            task = get_task(name)
            logits = np.load(path).astype(float)
            info = manifest["tasks"][name]
            if logits.shape[0] != info["total_rows"]:
                raise SystemExit(f"{name}: {logits.shape[0]} logit rows != {info['total_rows']}")
            extra = logits.shape[1] - len(task.codes)
            if not task.multilabel and extra > 0:
                if (logits.argmax(axis=1) >= len(task.codes)).any():
                    raise SystemExit(f"{name}: an unused logit column wins the argmax")
                logits = logits[:, : len(task.codes)]
            if logits.shape[1] != len(task.codes):
                raise SystemExit(f"{name}: {logits.shape[1]} logit columns != {len(task.codes)}")
            probs = expit(logits) if task.multilabel else softmax(logits, axis=1)
            rows = [json.loads(line) for line in (data_dir / info["file"]).open()]
            gold, pred = [], []
            for row in rows:
                p = probs[row["index"]]
                labels = np.flatnonzero(p > 0.5).tolist() if task.multilabel else [int(p.argmax())]
                record = {
                    "id": row["id"],
                    "task": name,
                    "index": row["index"],
                    "status": "ok",
                    "gold": row["gold"],
                    "prediction": labels,
                    "probabilities": {str(i): round(float(v), 6) for i, v in enumerate(p)},
                }
                out.write(json.dumps(record) + "\n")
                gold.append(row["gold"])
                pred.append(labels)
            summary[name] = {"n": len(rows), **score(name, gold, pred)}
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--logits", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.logits, args.data, args.output), indent=2))
