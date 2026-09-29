"""Compare System One answers between two serving configs from `modal_app.py::prefix_check`.

uv run python llm2jev_bench/compare_configs.py results/llm2jev/prefix-check.json staged reference
"""

import json
import sys

import numpy as np


def flatten(response):
    """(question, candidate) -> probability; choice answers give one entry per option."""
    out = {}
    for qid, answer in response["answers"].items():
        if answer["type"] == "noul":
            out[qid] = answer["noul"]
        else:
            out.update({f"{qid}/{k}": v for k, v in answer["probabilities"].items()})
    return out


def decisions(response, threshold=0.5):
    return {
        qid: (a["noul"] > threshold) if a["type"] == "noul" else a["choice"]
        for qid, a in response["answers"].items()
    }


def main():
    path, a, b = sys.argv[1:4]
    results = json.load(open(path))["results"]
    rows_a, rows_b = results[a]["rows"], results[b]["rows"]
    diffs, flips, n_decisions = [], 0, 0
    for ra, rb in zip(rows_a, rows_b, strict=True):
        pa, pb = flatten(ra["response"]), flatten(rb["response"])
        assert pa.keys() == pb.keys()
        diffs += [abs(pa[k] - pb[k]) for k in pa]
        da, db = decisions(ra["response"]), decisions(rb["response"])
        flips += sum(da[k] != db[k] for k in da)
        n_decisions += len(da)
    diffs = np.array(diffs)
    for name in (a, b):
        r = results[name]
        seconds = sum(x["seconds"] for x in r["rows"])
        print(
            f"{name}: {len(r['rows'])} requests, {seconds:.1f} s serial, "
            f"new tokens {r['new_tokens']:,}, cached {r['cached_tokens']:,}"
        )
    print(
        f"{len(diffs)} probabilities: max |diff| {diffs.max():.4f}, "
        f"p99 {np.percentile(diffs, 99):.4f}, mean {diffs.mean():.5f}"
    )
    print(f"decisions that differ (choice argmax or noul > 0.5): {flips} / {n_decisions}")


if __name__ == "__main__":
    main()
