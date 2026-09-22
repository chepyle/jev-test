"""Download only requested Parquet splits and freeze a reproducible sample."""

import json
import random
from pathlib import Path

from jev_test.storage import digest, file_digest, read_jsonl, write_json
from jev_test.tasks import CATALOG, DATASET_ID, DATASET_REVISION, TASK_NAMES, get_task


def normalize(name: str, index: int, row: dict) -> dict:
    task = get_task(name)
    text = row["context"] if name == "case_hold" else row["text"]
    if isinstance(text, list) and all(isinstance(paragraph, str) for paragraph in text):
        text = "\n\n".join(text)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{name}/{index}: missing document text")
    labels = row["labels"] if task.multilabel else [row["label"]]
    result = {
        "id": f"{name}/{index}",
        "task": name,
        "index": index,
        "text": text,
        "gold": task.validate_labels(labels),
    }
    if name == "case_hold":
        endings = row["endings"]
        if len(endings) != 5 or any(not isinstance(x, str) or not x.strip() for x in endings):
            raise ValueError(f"{name}/{index}: expected five nonempty holdings")
        result["endings"] = endings
    return result


def sample_indices(size: int, limit: int, seed: int) -> list[int]:
    if limit < 0 or size < 1:
        raise ValueError("limit must be nonnegative and split must be nonempty")
    return (
        sorted(random.Random(seed).sample(range(size), limit))
        if 0 < limit < size
        else list(range(size))
    )


def prepare(
    output: Path, tasks: list[str], split: str, limit: int, seed: int, cache_dir: Path | None = None
) -> dict:
    from datasets import load_dataset

    if output.exists() and any(output.iterdir()):
        raise ValueError(f"{output} is not empty; choose a new data directory")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format_version": 1,
        "dataset": DATASET_ID,
        "revision": DATASET_REVISION,
        "catalog_sha256": digest(CATALOG),
        "split": split,
        "seed": seed,
        "limit_per_task": limit,
        "tasks": {},
    }
    for name in tasks:
        print(f"Preparing {name}/{split} …", flush=True)
        url = f"hf://datasets/{DATASET_ID}@{DATASET_REVISION}/{name}/{split}-*.parquet"
        dataset = load_dataset(
            "parquet",
            data_files={split: url},
            split=split,
            cache_dir=str(cache_dir) if cache_dir else None,
        )
        task = get_task(name)
        feature = dataset.features["labels" if task.multilabel else "label"]
        names = feature.feature.names if task.multilabel else feature.names
        if list(task.codes) != names:
            raise ValueError(f"{name}: dataset label order differs from the pinned catalog")
        if len(dataset) != CATALOG["tasks"][name]["split_sizes"][split]:
            raise ValueError(f"{name}: unexpected split size for the pinned dataset")
        indices = sample_indices(len(dataset), limit, seed)
        path = output / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for index in indices:
                row = normalize(name, index, dataset[index])
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        manifest["tasks"][name] = {
            "file": path.name,
            "sha256": file_digest(path),
            "count": len(indices),
            "total_rows": len(dataset),
            "indices": indices,
            "fingerprint": dataset._fingerprint,
        }
    write_json(output / "manifest.json", manifest)
    return manifest


def load_prepared(directory: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("format_version") != 1 or manifest.get("catalog_sha256") != digest(CATALOG):
        raise ValueError("Prepared data format or label catalog does not match this installation")
    if manifest.get("dataset") != DATASET_ID or manifest.get("revision") != DATASET_REVISION:
        raise ValueError("Prepared data does not match the pinned LexGLUE dataset")
    if manifest.get("split") not in {"test", "validation"} or not manifest.get("tasks"):
        raise ValueError("Prepared data must contain tasks from the test or validation split")
    rows = []
    seen = set()
    for name, info in manifest["tasks"].items():
        if name not in TASK_NAMES or info["file"] != f"{name}.jsonl":
            raise ValueError(f"Invalid task or file in manifest: {name}")
        path = directory / info["file"]
        if file_digest(path) != info["sha256"]:
            raise ValueError(f"Data changed since preparation: {path}")
        task_rows = read_jsonl(path)
        expected_size = CATALOG["tasks"][name]["split_sizes"][manifest["split"]]
        if info["total_rows"] != expected_size or len(task_rows) != info["count"]:
            raise ValueError(f"{name}: invalid row count")
        if [row["index"] for row in task_rows] != info["indices"] or not task_rows:
            raise ValueError(f"{name}: invalid sample indices")
        for row in task_rows:
            index = row["index"]
            if (
                type(index) is not int
                or not 0 <= index < expected_size
                or row["task"] != name
                or row["id"] != f"{name}/{index}"
                or row["id"] in seen
            ):
                raise ValueError(f"{name}: invalid or duplicate example identity")
            seen.add(row["id"])
            get_task(name).validate_labels(row["gold"])
            if not isinstance(row["text"], str) or not row["text"].strip():
                raise ValueError(f"{name}: empty document")
            if name == "case_hold" and (
                len(row.get("endings", [])) != 5
                or any(not isinstance(x, str) or not x.strip() for x in row["endings"])
            ):
                raise ValueError("case_hold: expected five holdings")
        rows.extend(task_rows)
    return manifest, rows
