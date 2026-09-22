import json

import pytest

from jev_test.storage import digest, file_digest, write_json
from jev_test.tasks import CATALOG, DATASET_ID, DATASET_REVISION, TASK_NAMES, get_task


@pytest.fixture
def prepared(tmp_path):
    """Synthetic examples for pipeline testing; never presented as benchmark scores."""
    directory = tmp_path / "data"
    directory.mkdir()
    manifest = {
        "format_version": 1,
        "dataset": DATASET_ID,
        "revision": DATASET_REVISION,
        "catalog_sha256": digest(CATALOG),
        "split": "test",
        "seed": 42,
        "limit_per_task": 2,
        "tasks": {},
    }
    for name in TASK_NAMES:
        rows = []
        for index in range(2):
            row = {
                "id": f"{name}/{index}",
                "task": name,
                "index": index,
                "text": "A synthetic legal document for an offline test.",
                "gold": [] if get_task(name).multilabel and index == 1 else [0],
            }
            if name == "case_hold":
                row["endings"] = [f"Candidate holding {i}" for i in range(5)]
            rows.append(row)
        path = directory / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        manifest["tasks"][name] = {
            "file": path.name,
            "sha256": file_digest(path),
            "count": 2,
            "total_rows": CATALOG["tasks"][name]["split_sizes"]["test"],
            "indices": [0, 1],
            "fingerprint": "synthetic-test-fixture",
        }
    write_json(directory / "manifest.json", manifest)
    return directory


def fake_response(request, model="typesafe/jev-test-fixture"):
    payload = json.loads(request.content)
    answers = {}
    for name, question in payload["questions"].items():
        if question["type"] == "choice":
            answers[name] = {"type": "choice", "choice": "0"}
        else:
            answers[name] = {"type": "noul", "noul": 0.9 if name == "label_0" else 0.1}
    return {
        "id": "fixture",
        "model": model,
        "answers": answers,
        "usage": {"input_tokens": 100, "output_tokens": 10, "cost": 0.001},
    }
