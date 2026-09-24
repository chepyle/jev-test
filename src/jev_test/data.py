"""Download only requested Parquet splits and freeze a reproducible sample."""

import csv
import hashlib
import io
import json
import random
import urllib.request
from pathlib import Path

from jev_test.storage import digest, file_digest, read_jsonl, write_json
from jev_test.tasks import CATALOG, SUITES, catalog_for, get_task


def normalize(name: str, index: int, row: dict) -> dict:
    task = get_task(name)
    source = catalog_for(name)["tasks"][name].get("source")
    if source:
        label = row[source["label"]]
        if isinstance(label, str):
            if label not in task.codes:
                raise ValueError(f"{name}/{index}: unknown label {label!r}")
            label = task.codes.index(label)
        row = {"text": row[source["text"]], "label": label}
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


def fetch_verified(url: str, sha256: str, cache_dir: Path | None) -> bytes:
    """Download a pinned source file once and refuse it unless its SHA-256 matches."""
    cache = (cache_dir or Path.home() / ".cache" / "jev-test") / sha256
    if cache.exists():
        data = cache.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"Checksum mismatch for {url}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def load_intent_split(name: str, split: str, cache_dir: Path | None) -> tuple[list[dict], str]:
    """Rows and a fingerprint for an intent-detection split, from pinned sources only."""
    from datasets import load_dataset

    entry = catalog_for(name)["tasks"][name]
    source = entry["source"]
    if source["type"] == "csv":
        info = source["files"].get(split)
        if info is None:
            raise ValueError(f"{name} has no {split} split")
        text = fetch_verified(info["url"], info["sha256"], cache_dir).decode("utf-8")
        reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
        return list(reader), info["sha256"][:16]
    url = (
        f"hf://datasets/{source['repo']}@{source['revision']}/{source['config']}/{split}-*.parquet"
    )
    dataset = load_dataset(
        "parquet",
        data_files={split: url},
        split=split,
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    if dataset.features[source["label"]].names != entry["codes"]:
        raise ValueError(f"{name}: dataset label order differs from the pinned catalog")
    return [dataset[i] for i in range(len(dataset))], dataset._fingerprint


def prepare(
    output: Path, tasks: list[str], split: str, limit: int, seed: int, cache_dir: Path | None = None
) -> dict:
    from datasets import load_dataset

    suites = {catalog_for(name)["dataset"] for name in tasks}
    if len(suites) != 1:
        raise ValueError("Prepare tasks from one benchmark suite per data directory")
    catalog = SUITES[suites.pop()]
    for name in tasks:
        if split not in catalog["tasks"][name]["split_sizes"]:
            raise ValueError(f"{name} has no {split} split")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"{output} is not empty; choose a new data directory")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format_version": 1,
        "dataset": catalog["dataset"],
        "revision": catalog["revision"],
        "catalog_sha256": digest(catalog),
        "split": split,
        "seed": seed,
        "limit_per_task": limit,
        "tasks": {},
    }
    for name in tasks:
        print(f"Preparing {name}/{split} …", flush=True)
        if catalog is CATALOG:
            url = (
                f"hf://datasets/{CATALOG['dataset']}@{CATALOG['revision']}/{name}/{split}-*.parquet"
            )
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
            fingerprint = dataset._fingerprint
        else:
            dataset, fingerprint = load_intent_split(name, split, cache_dir)
        if len(dataset) != catalog["tasks"][name]["split_sizes"][split]:
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
            "fingerprint": fingerprint,
        }
    write_json(output / "manifest.json", manifest)
    return manifest


def load_prepared(directory: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((directory / "manifest.json").read_text())
    catalog = SUITES.get(manifest.get("dataset"))
    if catalog is None or manifest.get("revision") != catalog["revision"]:
        raise ValueError("Prepared data does not match a pinned benchmark dataset")
    if manifest.get("format_version") != 1 or manifest.get("catalog_sha256") != digest(catalog):
        raise ValueError("Prepared data format or label catalog does not match this installation")
    if manifest.get("split") not in {"test", "validation"} or not manifest.get("tasks"):
        raise ValueError("Prepared data must contain tasks from the test or validation split")
    rows = []
    seen = set()
    for name, info in manifest["tasks"].items():
        if name not in catalog["tasks"] or info["file"] != f"{name}.jsonl":
            raise ValueError(f"Invalid task or file in manifest: {name}")
        path = directory / info["file"]
        if file_digest(path) != info["sha256"]:
            raise ValueError(f"Data changed since preparation: {path}")
        task_rows = read_jsonl(path)
        expected_size = catalog["tasks"][name]["split_sizes"][manifest["split"]]
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
