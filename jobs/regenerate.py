"""Run scripts/regenerate_analysis.sh under the longrun job layout.

Usage: uv run python jobs/regenerate.py <job-id> <out-dir> [jobs]

Every output is written atomically, so resume is the same command: it passes RESUME=1 and
the script skips outputs already present. Heartbeats count finished outputs. On SIGTERM or
SIGINT the script's whole process group is killed, so no analysis worker is orphaned.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/jake/.claude/skills/longrun")
from jobstate import Job  # noqa: E402

TOTAL = 29  # bootstrap outputs listed in scripts/regenerate_analysis.sh


def main() -> None:
    job_id, out = sys.argv[1], Path(sys.argv[2])
    workers = sys.argv[3] if len(sys.argv) > 3 else "4"
    cmd = f"uv run python jobs/regenerate.py {job_id} {out} {workers}"
    child = {"proc": None}

    def stop():
        proc = child["proc"]
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=60)

    def finished() -> int:
        return sum(1 for p in out.glob("*.json") if p.stat().st_size)

    with Job(job_id, total=TOTAL, cmd=cmd, resume_cmd=cmd, stall_seconds=1800,
             on_terminate=stop) as job:  # fmt: skip
        out.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "OUT": str(out), "JOBS": workers, "RESUME": "1"}
        child["proc"] = subprocess.Popen(
            ["scripts/regenerate_analysis.sh"], env=env, start_new_session=True
        )
        while child["proc"].poll() is None:
            job.beat(finished())
            time.sleep(15)
        job.beat(finished())
        if child["proc"].returncode:
            raise RuntimeError(f"regenerate_analysis.sh exited {child['proc'].returncode}")


if __name__ == "__main__":
    main()
