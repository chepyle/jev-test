"""Write a control item set (a subset of a prepared-data directory) for the paired control runs.

    uv run python scripts/prepare_control_subset.py SOURCE OUTPUT TASK[:N] [TASK[:N] ...]

`TASK` keeps the whole task; `TASK:N` keeps N documents drawn with
`jev_test.data.sample_indices` (seed 42, the prepare default), so every control arm that
names the same sample gets the same ids. Rows are copied unchanged, so request bytes match
the source runs for the same ids. The sets used in RESULTS.md:

    data/control-full      from data/full-test:        ecthr_a ecthr_b scotus unfair_tos eurlex:500
    data/control-bertctx   from data/full-test-bertctx: ecthr_a ecthr_b scotus eurlex:500
    data/multilabel-control from data/full-test:       ecthr_a ecthr_b unfair_tos eurlex:500
"""

import hashlib
import json
import sys
from pathlib import Path

from jev_test.data import sample_indices
from jev_test.storage import read_jsonl


def main(source: Path, output: Path, specs: list[str]) -> None:
    manifest = json.loads((source / "manifest.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    tasks = {}
    for spec in specs:
        task, _, size = spec.partition(":")
        info = dict(manifest["tasks"][task])
        rows = read_jsonl(source / info["file"])
        if size:
            keep = set(sample_indices(info["total_rows"], int(size), 42))
            rows = [r for r in rows if r["index"] in keep]
        path = output / info["file"]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        info.update(
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            count=len(rows),
            indices=[r["index"] for r in rows],
        )
        tasks[task] = info
        print(output, task, len(rows))
    manifest["tasks"] = tasks
    manifest["derived"] = {
        **manifest.get("derived", {}),
        "subset_of": str(source),
        "subset": specs,
        "script": "scripts/prepare_control_subset.py",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:])
