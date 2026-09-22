"""Command-line interface: prepare data, run inference, and report offline."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from filelock import FileLock, Timeout

from jev_test.client import DEFAULT_ENDPOINT, DEFAULT_MODEL
from jev_test.data import prepare
from jev_test.report import write_report
from jev_test.runner import run_benchmark
from jev_test.tasks import TASK_NAMES, get_task


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Benchmark Jev on LexGLUE via OpenRouter System One"
    )
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("tasks", help="List supported tasks and label counts")
    data = commands.add_parser("prepare", help="Freeze official data and a deterministic sample")
    data.add_argument("--tasks", nargs="+", choices=["all", *TASK_NAMES], default=["all"])
    data.add_argument("--split", choices=["test", "validation"], default="test")
    data.add_argument("--limit", type=int, default=10, help="Examples per task; 0 means full split")
    data.add_argument("--seed", type=int, default=42)
    data.add_argument("--output", type=Path, required=True)
    data.add_argument("--cache-dir", type=Path, default=Path(".cache/huggingface/datasets"))
    run = commands.add_parser("run", help="Run inference against a frozen prepared dataset")
    run.add_argument("--data", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--model", default=DEFAULT_MODEL)
    run.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    run.add_argument(
        "--threshold", type=float, default=0.5, help="Select labels with p > threshold"
    )
    run.add_argument(
        "--max-chars",
        type=int,
        default=48_000,
        help="Head/tail document character cap; 0 disables truncation",
    )
    run.add_argument("--concurrency", type=int, default=4)
    run.add_argument(
        "--retries", type=int, default=4, help="Transient retries after the first attempt"
    )
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--retry-failed", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="Write requests without API calls")
    report = commands.add_parser(
        "report", help="Recompute metrics from an existing prediction ledger"
    )
    report.add_argument("directory", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "tasks":
            for name in TASK_NAMES:
                task = get_task(name)
                print(f"{name:12} {task.kind:10} {len(task.codes):3} labels")
        elif args.command == "prepare":
            if args.limit < 0:
                raise ValueError("--limit must be nonnegative")
            tasks = list(TASK_NAMES) if "all" in args.tasks else list(dict.fromkeys(args.tasks))
            manifest = prepare(
                args.output, tasks, args.split, args.limit, args.seed, args.cache_dir
            )
            count = sum(info["count"] for info in manifest["tasks"].values())
            print(f"Prepared {count} examples in {args.output}")
        elif args.command == "run":
            result = asyncio.run(
                run_benchmark(
                    args.data,
                    args.output,
                    model=args.model,
                    endpoint=args.endpoint,
                    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                    threshold=args.threshold,
                    max_chars=args.max_chars,
                    concurrency=args.concurrency,
                    retries=args.retries,
                    timeout=args.timeout,
                    resume=args.resume,
                    retry_failed=args.retry_failed,
                    dry_run=args.dry_run,
                )
            )
            if args.dry_run:
                print(
                    f"Previewed {result['requests']} requests in {args.output}; no API calls made."
                )
            else:
                print(f"Report: {args.output / 'report.md'}")
                if not result["complete"] or result["mixed_models"]:
                    print("Run incomplete or mixed: see report and resume guidance in README.")
                    sys.exit(2)
        elif args.command == "report":
            with FileLock(args.directory / ".run.lock", timeout=0):
                write_report(args.directory)
            print(f"Report: {args.directory / 'report.md'}")
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Completed calls are checkpointed; rerun with --resume.", file=sys.stderr
        )
        sys.exit(130)
    except (ValueError, OSError, Timeout) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)
