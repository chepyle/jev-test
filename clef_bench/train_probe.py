"""Training-split exposure probe for Clef-flash, with Jev as the control (PREREG-train-probe.md).

    uv run python clef_bench/prepare_train_probe.py
    uv run --env-file .env python clef_bench/train_probe.py run clef-flash
    uv run python clef_bench/train_probe.py run jev            # OPENROUTER_API_KEY from the env
    uv run python clef_bench/train_probe.py score > analysis/clef-flash-train-probe.json

`jev-bench run` refuses training-split data, which keeps training items out of benchmark
runs. This probe scores them on purpose, so it sends the same requests (`build_request`,
48,000-character cap) through the same client and parser, and appends one JSON line per
query to `results/<model>-intents-train-probe/predictions.jsonl`. Re-running `run` skips
queries already answered.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import numpy as np

from jev_test.analysis import interval, load_source
from jev_test.client import DEFAULT_ENDPOINT, SystemOneClient
from jev_test.questions import build_request, parse_response

DATA = Path("data/intents-train-probe")
CLEF_URL = "https://jakealbrecht--jev-test-clef-flash-server-api.modal.run/v1/systemone"
TARGETS = {
    "clef-flash": ("clef-flash", CLEF_URL, "LLM2JEV_API_KEY", 16),
    "jev": ("typesafe/jev-1.13", DEFAULT_ENDPOINT, "OPENROUTER_API_KEY", 4),
}
TEST_LEDGERS = {
    "clef-flash": "results/clef-flash-intents-test/predictions.jsonl",
    "jev": "results/jev-intents-test/predictions.jsonl",
}
RESAMPLES = 1000
TRAIN_SEED = 1


def ledger(name: str) -> Path:
    return Path(f"results/{name}-intents-train-probe/predictions.jsonl")


async def run(name: str) -> None:
    model, endpoint, key_env, concurrency = TARGETS[name]
    out = ledger(name)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {i for records in load_source(out).values() for i in records} if out.exists() else set()
    rows = [
        json.loads(line)
        for task in ("banking77", "clinc150")
        for line in (DATA / f"{task}.jsonl").open()
    ]
    todo = [r for r in rows if r["id"] not in done]
    print(f"{name}: {len(todo)} to send, {len(done)} already answered", flush=True)
    gate = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=600) as http:
        client = SystemOneClient(http, os.environ[key_env], endpoint=endpoint)

        async def one(row: dict) -> None:
            payload, _ = build_request(row, model, 48000)
            async with gate:
                result = await client.predict(payload)
            prediction, probabilities = parse_response(row["task"], result.body, 0.5)
            record = {
                "id": row["id"],
                "task": row["task"],
                "gold": row["gold"],
                "status": "ok",
                "prediction": prediction,
                "probabilities": probabilities,
                "response": result.body,
            }
            with out.open("a") as fh:
                fh.write(json.dumps(record) + "\n")

        await asyncio.gather(*(one(r) for r in todo))
    print(f"{name}: done", flush=True)


def accuracy(path: str, seed: int) -> dict:
    """Accuracy and its bootstrap draws per task, over records sorted by id.

    Ledgers are in async completion order, so sorting is what makes two models' draws land
    on the same queries (the difference-in-differences is paired by query). The draw loop
    matches `jev_test.analysis.analyze_task`, so with seed 0 the test intervals equal those
    in analysis/intents-*.json for the same ledger."""
    out = {}
    for task, records in load_source(Path(path)).items():
        ids = sorted(records)
        hits = np.array([records[i]["prediction"] == records[i]["gold"] for i in ids], float)
        rng = np.random.default_rng(seed)
        samples = np.array([rng.integers(0, len(ids), len(ids)) for _ in range(RESAMPLES)])
        out[task] = {"ids": ids, "acc": float(hits.mean()), "boot": hits[samples].mean(1)}
    return out


def score() -> dict:
    """Train draws use seed 1 and test draws seed 0, so the two splits resample independently;
    both models share each split's draws, which pairs them by query."""
    result = {"resamples": RESAMPLES, "seed": {"train": TRAIN_SEED, "test": 0}, "models": {}}
    gaps, ids = {}, {}
    for name in TARGETS:
        train = accuracy(str(ledger(name)), TRAIN_SEED)
        test = accuracy(TEST_LEDGERS[name], 0)
        result["models"][name] = {}
        for task in ("banking77", "clinc150"):
            ids.setdefault(task, (train[task]["ids"], test[task]["ids"]))
            if (train[task]["ids"], test[task]["ids"]) != ids[task]:
                raise ValueError(f"{name}/{task}: queries differ from the other model's")
            gap = train[task]["boot"] - test[task]["boot"]
            gaps[name, task] = gap
            result["models"][name][task] = {
                "train_n": len(train[task]["ids"]),
                "train_acc": train[task]["acc"],
                "train_ci95": interval(train[task]["boot"]),
                "test_n": len(test[task]["ids"]),
                "test_acc": test[task]["acc"],
                "test_ci95": interval(test[task]["boot"]),
                "train_minus_test": train[task]["acc"] - test[task]["acc"],
                "train_minus_test_ci95": interval(gap),
            }
    result["difference_in_differences"] = {
        task: {
            "clef_gap_minus_jev_gap": float(
                result["models"]["clef-flash"][task]["train_minus_test"]
                - result["models"]["jev"][task]["train_minus_test"]
            ),
            "ci95": interval(gaps["clef-flash", task] - gaps["jev", task]),
        }
        for task in ("banking77", "clinc150")
    }
    return result


if __name__ == "__main__":
    if sys.argv[1] == "run":
        asyncio.run(run(sys.argv[2]))
    else:
        print(json.dumps(score(), indent=2))
