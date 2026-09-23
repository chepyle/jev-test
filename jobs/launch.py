"""Supervise a jev-bench run under the longrun job layout.

Usage: uv run python jobs/launch.py <job-id> <data-dir> <output-dir> [jev-bench run args...]

The runner checkpoints every call to <output>/predictions.jsonl, so resume is
`--resume` on the same command. This wrapper adds what the runner lacks:
heartbeats from the ledger, 30s+ exponential backoff on throttles (the client's
own retries top out at ~16s and then stop the run), and a hard stop on
permanent errors such as 401/402.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, "/home/jake/.claude/skills/longrun")
from jobstate import Job  # noqa: E402

TRANSIENT = re.compile(r"HTTP (408|429|5\d\d)|Transport failure")
MAX_RELAUNCHES = 8
POLL_SECONDS = 15


def ledger_state(path):
    last = {}
    try:
        with open(path) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # torn tail; the runner repairs it on resume
                last[rec["id"]] = rec
    except FileNotFoundError:
        pass
    ok = sum(1 for r in last.values() if r["status"] == "ok")
    errors = [r for r in last.values() if r["status"] == "error"]
    return ok, errors


def main():
    job_id, data, output, *extra = sys.argv[1:]
    with open(os.path.join(data, "manifest.json")) as fh:
        total = sum(v["count"] for v in json.load(fh)["tasks"].values())
    base = ["uv", "run", "jev-bench", "run", "--data", data, "--output", output, *extra]
    cmd = " ".join(["uv run python jobs/launch.py", job_id, data, output, *extra])
    ledger = os.path.join(output, "predictions.jsonl")
    child = {"proc": None}

    def stop_child():
        proc = child["proc"]
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGINT)  # runner's graceful path: flush + report
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
        ok, errors = ledger_state(ledger)
        job.beat(ok, errors=len(errors))  # so the "interrupted" beat carries the true count

    with Job(
        job_id, total=total, cmd=cmd, resume_cmd=cmd, stall_seconds=2400, on_terminate=stop_child
    ) as job:
        # Backoff escalates only across consecutive launches that made no progress. An
        # isolated 529 after a thousand good requests restarts at the 30 s base; the old
        # count-every-relaunch policy reached 1355 s and would quit after 8 scattered 529s.
        throttles = 0
        launch = 0
        best_ok, _ = ledger_state(ledger)
        while True:
            argv = list(base)
            if os.path.exists(os.path.join(output, "manifest.json")):
                # Re-send checkpointed failures too; permanent ones stop the loop below.
                argv += ["--resume", "--retry-failed"]
            job.incident("launch {}: {}".format(launch, " ".join(argv)))
            launch += 1
            child["proc"] = proc = subprocess.Popen(argv)
            while proc.poll() is None:
                ok, errors = ledger_state(ledger)
                job.beat(ok, errors=len(errors))
                time.sleep(POLL_SECONDS)
            ok, errors = ledger_state(ledger)
            job.beat(ok, errors=len(errors), exit_code=proc.returncode)
            if proc.returncode == 0:
                return
            messages = sorted({e.get("error", "") for e in errors})
            job.incident(
                f"runner exit {proc.returncode}; ok={ok} errors={len(errors)} {messages[:5]}"
            )
            if not errors or not all(TRANSIENT.search(m) for m in messages):
                raise RuntimeError(f"permanent failure, not resuming: {messages[:5]}")
            if ok > best_ok:
                best_ok, throttles = ok, 0
            if throttles >= MAX_RELAUNCHES:
                raise RuntimeError(f"gave up after {MAX_RELAUNCHES} relaunches without progress")
            job.sleep_backoff(throttles, reason=f"transient errors {messages[:3]}")
            throttles += 1


if __name__ == "__main__":
    main()
