"""Resumable, heartbeat-publishing launcher for `jev-bench run --protocol decisions`.

Wraps run_benchmark with longrun's Job (heartbeat, pidfile, incident log). The prediction
ledger is the checkpoint: one fsynced record per call, so a kill loses at most in-flight calls.
Resume with the same command plus --resume.
"""

import argparse
import asyncio
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, "/home/jake/.claude/skills/longrun")
from jobstate import Job  # noqa: E402

from jev_test.runner import run_benchmark  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--job-id", required=True)
p.add_argument("--data", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--total", type=int, required=True)
p.add_argument("--concurrency", type=int, default=12)
p.add_argument("--resume", action="store_true")
args = p.parse_args()

ledger = args.output / "predictions.jsonl"


def count() -> int:
    try:
        with ledger.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


with Job(args.job_id, total=args.total, stall_seconds=300) as job:
    stop = threading.Event()

    def beats() -> None:
        while not stop.wait(10):
            job.beat(count())

    threading.Thread(target=beats, daemon=True).start()
    if args.resume:
        job.incident(f"resuming with {count()} ledger records")
    result = asyncio.run(
        run_benchmark(
            args.data,
            args.output,
            model="gpt-6-luna",
            endpoint="https://api.openai.com/v1/decisions",
            api_key=os.environ["OPENAI_API_KEY"],
            concurrency=args.concurrency,
            resume=args.resume,
            retry_failed=args.resume,
            protocol="decisions",
        )
    )
    stop.set()
    job.beat(count())
    if not result["complete"]:
        job.incident("run incomplete: see report")
        raise SystemExit(2)
