"""Recompute reports offline from the append-only prediction ledger."""

import csv
import json
import math
import statistics
from pathlib import Path

from jev_test.metrics import aggregate, score
from jev_test.storage import read_jsonl, write_json
from jev_test.tasks import TASK_NAMES, get_task


def resolved_models(records: list[dict]) -> list[str]:
    return sorted(
        {
            row["response"]["model"]
            for row in records
            if isinstance(row.get("response"), dict)
            and isinstance(row["response"].get("model"), str)
            and row["response"]["model"]
        }
    )


def usage_number(usage: dict, name: str) -> int | float | None:
    value = usage.get(name)
    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
        return value
    return None


def latest_records(records: list[dict]) -> dict[str, dict]:
    latest = {}
    for record in records:
        if record["id"] in latest and latest[record["id"]]["status"] == "ok":
            raise ValueError(f"Ledger has a repeated successful example: {record['id']}")
        latest[record["id"]] = record
    return latest


def make_report(manifest: dict, records: list[dict]) -> dict:
    latest = latest_records(records)
    data = manifest["data"]
    expected_ids = {f"{name}/{i}" for name, info in data["tasks"].items() for i in info["indices"]}
    for row in records:
        if row["id"] not in expected_ids or row["id"] != f"{row['task']}/{row['index']}":
            raise ValueError("Ledger contains an example outside this run")
        if row["status"] not in {"ok", "error"}:
            raise ValueError("Ledger contains an invalid status")
        get_task(row["task"]).validate_labels(row["gold"])
    models = resolved_models(records)
    tasks = {}
    for name, info in data["tasks"].items():
        rows = [r for r in latest.values() if r["task"] == name]
        successful = [r for r in rows if r["status"] == "ok"]
        failed = len(rows) - len(successful)
        tasks[name] = {
            "expected": info["count"],
            "successful": len(successful),
            "failed": failed,
            "pending": info["count"] - len(rows),
            "coverage": len(successful) / info["count"],
            "complete": len(successful) == info["count"],
            "full_split": info["count"] == info["total_rows"],
            "truncated": sum(r["input"]["truncated"] for r in successful),
            "scores": score(
                name, [r["gold"] for r in successful], [r["prediction"] for r in successful]
            )
            if successful
            else None,
        }
    complete = all(task["complete"] for task in tasks.values())
    single_model = len(models) == 1
    full_test = (
        data["split"] == "test"
        and set(tasks) == set(TASK_NAMES)
        and all(task["full_split"] for task in tasks.values())
    )
    combined = (
        aggregate([task["scores"] for task in tasks.values()])
        if (complete and single_model)
        else None
    )
    usage = [
        r["response"]["usage"]
        for r in records
        if isinstance(r.get("response"), dict) and isinstance(r["response"].get("usage"), dict)
    ]
    costs = [cost for u in usage if (cost := usage_number(u, "cost")) is not None]
    latencies = [r["latency_seconds"] for r in records]
    total_cost = sum(costs) if costs else None
    return {
        "protocol": "zero-shot System One; no training or test-label tuning",
        "split": data["split"],
        "requested_model": manifest["config"]["model"],
        "resolved_models": models,
        "complete": complete,
        "mixed_models": len(models) > 1,
        "full_lexglue_test": full_test,
        "tasks": tasks,
        "selected_tasks_aggregate": combined,
        "lexglue_aggregate": combined if full_test else None,
        "usage": {
            "recorded_calls": len(records),
            "http_attempts": sum(r["attempts"] for r in records),
            "input_tokens": sum(usage_number(u, "input_tokens") or 0 for u in usage),
            "output_tokens": sum(usage_number(u, "output_tokens") or 0 for u in usage),
            "reported_cost_usd": total_cost,
            "calls_with_reported_cost": len(costs),
            "mean_latency_seconds": statistics.mean(latencies) if latencies else None,
        },
        "notes": [
            "F1 values are in [0, 1]; Markdown displays percentages.",
            "Partial task scores use successful examples only and are diagnostic.",
            "Aggregates require complete coverage and one resolved model.",
            "A LexGLUE aggregate additionally requires all seven complete test splits.",
            "Cost covers returned usage; failed, retried, or interrupted requests may add charges.",
            "Published LexGLUE baselines are supervised; this protocol is zero-shot.",
        ],
    }


def markdown(report: dict) -> str:
    lines = [
        "# Jev on LexGLUE",
        "",
        f"Model: `{report['requested_model']}`. Split: `{report['split']}`. "
        f"Complete: **{report['complete']}**.",
        "",
        "Resolved models: " + (", ".join(report["resolved_models"]) or "none"),
        "",
        "Protocol: zero-shot System One classification. F1 is shown as a percentage.",
        "",
        "| Task | Scored / expected | Failed | Micro-F1 | Macro-F1 | Truncated |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, task in report["tasks"].items():
        scores = task["scores"]
        micro = f"{100 * scores['micro_f1']:.2f}" if scores else "—"
        macro = f"{100 * scores['macro_f1']:.2f}" if scores else "—"
        lines.append(
            f"| {name} | {task['successful']} / {task['expected']} | {task['failed']} "
            f"| {micro} | {macro} | {task['truncated']} |"
        )
    if report["selected_tasks_aggregate"]:
        title = (
            "Full LexGLUE test aggregate"
            if report["lexglue_aggregate"]
            else ("Selected sample/task aggregate (not a full LexGLUE test score)")
        )
        lines.extend(["", title, "", "| Average | Micro-F1 | Macro-F1 |", "| --- | ---: | ---: |"])
        for average in ("arithmetic", "harmonic", "geometric"):
            values = report["selected_tasks_aggregate"]
            lines.append(
                f"| {average} | {100 * values['micro_f1'][average]:.2f} "
                f"| {100 * values['macro_f1'][average]:.2f} |"
            )
    else:
        lines.extend(["", "Aggregate unavailable: incomplete coverage or mixed model versions."])
    usage = report["usage"]
    cost = usage["reported_cost_usd"]
    lines.extend(
        [
            "",
            f"Reported API cost: {'unknown' if cost is None else f'${cost:.6f}'}. "
            f"Input tokens: {usage['input_tokens']:,}. "
            f"Output tokens: {usage['output_tokens']:,}.",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report["notes"])
    return "\n".join(lines) + "\n"


def write_report(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    records = read_jsonl(directory / "predictions.jsonl")
    report = make_report(manifest, records)
    write_json(directory / "metrics.json", report)
    (directory / "report.md").write_text(markdown(report))
    with (directory / "metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "task",
                "expected",
                "successful",
                "failed",
                "pending",
                "truncated",
                "micro_f1",
                "macro_f1",
                "exact_match",
            ],
        )
        writer.writeheader()
        for name, task in report["tasks"].items():
            writer.writerow(
                {
                    "task": name,
                    **{
                        k: task[k]
                        for k in ("expected", "successful", "failed", "pending", "truncated")
                    },
                    **(task["scores"] or {}),
                }
            )
    return report
