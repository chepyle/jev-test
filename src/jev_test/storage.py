"""Small, auditable JSON artifacts; each completed API call is durable."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path: Path, *, repair_tail: bool = False) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    offset = 0
    with path.open("rb") as handle:
        lines = handle.readlines()
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("expected a JSON object")
        except (ValueError, UnicodeDecodeError) as error:
            if repair_tail and index == len(lines) - 1 and not line.endswith(b"\n"):
                with path.open("r+b") as handle:
                    handle.truncate(offset)
                break
            raise ValueError(f"Corrupt JSONL: {path}, line {index + 1}") from error
        rows.append(row)
        offset += len(line)
    # A complete JSON object may have been written before its newline on interruption.
    if repair_tail and lines and len(rows) == len(lines) and not lines[-1].endswith(b"\n"):
        with path.open("ab") as handle:
            handle.write(b"\n")
    return rows
