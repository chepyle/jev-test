"""Bounded asynchronous inference with durable checkpoints and strict resume checks."""

import asyncio
import json
import math
import platform
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import httpx
from filelock import FileLock

from jev_test.chat import CHAT_PROTOCOL_VERSION, build_chat_request, parse_chat_response
from jev_test.client import (
    CHAT_ENDPOINT,
    DEFAULT_ENDPOINT,
    ChatClient,
    InferenceError,
    SystemOneClient,
)
from jev_test.data import load_prepared
from jev_test.questions import PROTOCOL_VERSION
from jev_test.questions import build_request as systemone_request
from jev_test.questions import parse_response as systemone_parse
from jev_test.report import latest_records, resolved_models, write_report
from jev_test.storage import append_jsonl, digest, file_digest, read_jsonl, write_json


def protocol_digest() -> str:
    root = Path(__file__).parent
    return digest(
        {
            name: file_digest(root / name)
            for name in (
                "tasks.py",
                "questions.py",
                "chat.py",
                "client.py",
                "metrics.py",
                "runner.py",
            )
        }
    )


async def run_benchmark(
    data_dir: Path,
    output: Path,
    *,
    model: str,
    endpoint: str,
    api_key: str = "",
    threshold: float = 0.5,
    max_chars: int = 48_000,
    concurrency: int = 4,
    retries: int = 4,
    timeout: float = 120,
    resume: bool = False,
    retry_failed: bool = False,
    dry_run: bool = False,
    protocol: str = "systemone",
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    if protocol not in ("systemone", "chat"):
        raise ValueError("protocol must be 'systemone' or 'chat'")
    chat = protocol == "chat"
    build_request, parse_response = (
        (build_chat_request, parse_chat_response) if chat else (systemone_request, systemone_parse)
    )
    if chat and endpoint == DEFAULT_ENDPOINT:
        endpoint = CHAT_ENDPOINT
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be finite and in [0, 1]")
    if concurrency < 1 or retries < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("concurrency/timeout must be positive and retries nonnegative")
    if retry_failed and not resume:
        raise ValueError("--retry-failed requires --resume")
    if dry_run and resume:
        raise ValueError("--dry-run cannot be combined with --resume")
    if not dry_run and not api_key:
        raise ValueError("Set OPENROUTER_API_KEY, or use --dry-run to inspect requests")
    data_manifest, examples = load_prepared(data_dir)
    # Validate truncation before creating artifacts or making any requests.
    build_request(examples[0], model, max_chars)
    config = {
        "model": model,
        "endpoint": endpoint,
        "threshold": threshold,
        "max_chars": max_chars,
        "protocol": protocol,
        "protocol_version": CHAT_PROTOCOL_VERSION if chat else PROTOCOL_VERSION,
        "protocol_sha256": protocol_digest(),
        "data_sha256": digest(data_manifest),
    }
    output.mkdir(parents=True, exist_ok=True)
    with FileLock(output / ".run.lock", timeout=0):
        manifest_path = output / "manifest.json"
        if dry_run:
            if any(p.name != ".run.lock" for p in output.iterdir()):
                raise ValueError("Dry-run output must be empty; choose a new directory")
            truncated = 0
            with (output / "requests.jsonl").open("w", encoding="utf-8") as handle:
                for row in examples:
                    request, info = build_request(row, model, max_chars)
                    truncated += info["truncated"]
                    handle.write(
                        json.dumps(
                            {"id": row["id"], "request": request, "input": info}, ensure_ascii=False
                        )
                        + "\n"
                    )
            summary = {
                "dry_run": True,
                "requests": len(examples),
                "truncated": truncated,
                "config": config,
                "data": data_manifest,
            }
            write_json(output / "preview.json", summary)
            return summary
        if manifest_path.exists():
            if not resume:
                raise ValueError(
                    "Run already exists; use --resume or choose a new output directory"
                )
            manifest = json.loads(manifest_path.read_text())
            if manifest["config"] != config or manifest["data"] != data_manifest:
                raise ValueError("Resume refused: data, model, protocol, or settings changed")
        else:
            if resume:
                raise ValueError("Cannot resume: run manifest does not exist")
            if any(p.name != ".run.lock" for p in output.iterdir()):
                raise ValueError("Output directory contains other files; choose a new directory")
            manifest = {
                "format_version": 1,
                "created_at": datetime.now(UTC).isoformat(),
                "config": config,
                "data": data_manifest,
                "environment": {
                    "python": platform.python_version(),
                    "packages": {
                        name: version(name)
                        for name in (
                            "jev-test",
                            "datasets",
                            "httpx",
                            "scikit-learn",
                        )
                    },
                },
            }
            write_json(manifest_path, manifest)
        ledger = output / "predictions.jsonl"
        records = read_jsonl(ledger, repair_tail=resume)
        previous = latest_records(records)
        by_id = {row["id"]: row for row in examples}
        for record in records:
            row = by_id.get(record["id"])
            if row is None or row["gold"] != record["gold"]:
                raise ValueError("Resume refused: ledger does not match prepared examples")
            request, _ = build_request(row, model, max_chars)
            if record["request_sha256"] != digest(request):
                raise ValueError("Resume refused: saved request differs from current protocol")
        # Validate ledger integrity before issuing any paid requests.
        write_report(output)
        pending = [
            row
            for row in examples
            if row["id"] not in previous
            or (retry_failed and previous[row["id"]]["status"] == "error")
        ]
        models = set(resolved_models(records))
        if len(models) > 1:
            raise ValueError(
                "Run contains mixed model versions; start a new run with a pinned model"
            )
        print(
            f"{len(pending)} requests pending; {len(examples) - len(pending)} checkpointed.",
            flush=True,
        )
        queue = asyncio.Queue()
        for row in pending:
            queue.put_nowait(row)
        stopped = asyncio.Event()
        completed = 0
        async with httpx.AsyncClient(
            timeout=timeout, transport=transport, follow_redirects=False
        ) as http:
            factory = ChatClient if chat else SystemOneClient
            client = factory(http, api_key, endpoint=endpoint, retries=retries)

            async def worker() -> None:
                nonlocal completed
                while not stopped.is_set():
                    try:
                        row = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    payload, info = build_request(row, model, max_chars)
                    record = {
                        "id": row["id"],
                        "task": row["task"],
                        "index": row["index"],
                        "gold": row["gold"],
                        "request_sha256": digest(payload),
                        "input": info,
                        "attempts": 0,
                    }
                    start = time.monotonic()
                    try:
                        result = await client.predict(payload)
                        record.update(response=result.body, attempts=result.attempts)
                        prediction, probabilities = parse_response(
                            row["task"], result.body, threshold
                        )
                        record.update(
                            status="ok", prediction=prediction, probabilities=probabilities
                        )
                        models.add(result.body["model"])
                        if len(models) > 1:
                            print(
                                "Model version changed during the run; stopping. "
                                "Start a new run using a pinned model ID.",
                                flush=True,
                            )
                            stopped.set()
                    except (InferenceError, ValueError) as error:
                        record.update(status="error", error=str(error))
                        if isinstance(error, InferenceError):
                            record["attempts"] = error.attempts
                        print(f"{row['id']}: {error}. Stopping new requests.", flush=True)
                        stopped.set()
                    record["latency_seconds"] = time.monotonic() - start
                    record["completed_at"] = datetime.now(UTC).isoformat()
                    append_jsonl(ledger, record)
                    completed += 1
                    if completed % 10 == 0 or completed == len(pending) or stopped.is_set():
                        print(f"Saved {completed}/{len(pending)} new results.", flush=True)

            workers = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(pending)))]
            try:
                await asyncio.gather(*workers)
            finally:
                for task in workers:
                    task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
                write_report(output)
        return write_report(output)
