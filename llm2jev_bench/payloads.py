"""Write System One payloads for the first N rows of each task, as `jev-bench run` builds them.

    uv run python llm2jev_bench/payloads.py data/smoke50 data/intents-smoke --per-task 3 \
        --output results/llm2jev/prefix-payloads.jsonl
"""

import argparse
import json
from pathlib import Path

from jev_test.questions import build_request

SERVED_NAME = "qwen3.5-4b"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", nargs="+")
    parser.add_argument("--per-task", type=int, default=3)
    parser.add_argument("--max-chars", type=int, default=48000)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for data in map(Path, args.data):
            manifest = json.loads((data / "manifest.json").read_text())
            for task in manifest["tasks"]:
                with (data / f"{task}.jsonl").open() as rows:
                    for _, line in zip(range(args.per_task), rows, strict=False):
                        payload, _ = build_request(json.loads(line), SERVED_NAME, args.max_chars)
                        fh.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    main()
