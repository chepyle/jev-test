"""Cut each LexGLUE test document to the text the fine-tuned BERT baseline actually read.

    uv run --with tokenizers python bert/context_matched.py data/full-test data/full-test-bertctx

Jev reads up to 48,000 characters (about 12k tokens); the BERT baselines read what upstream
coastalcph/lex-glue (commit 419a49d, `experiments/*.py` defaults, no overrides in
`bert/lexglue_modal.py`) feeds them through the bert-base-uncased tokenizer:

- ECtHR A/B: the first 64 fact paragraphs, each cut to 128 tokens (hierarchical BERT);
- SCOTUS: `re.split('\\n{2,}', text)[:64]`, each segment cut to 128 tokens (hierarchical);
- EUR-LEX, LEDGAR: the first 512 tokens; UNFAIR-ToS: the first 128 tokens;
- CaseHOLD: each (context, holding) pair cut to 256 tokens with `longest_first`, so the
  context loses its tail; we keep the longest context prefix BERT saw with any holding.

Token limits include [CLS]/[SEP]. The kept text is the original characters up to the end of
the last kept word piece (tokenizer offsets), so casing and spacing are unchanged. ECtHR
paragraphs come from the pinned Parquet test split and are checked to rejoin to the prepared
text. The output directory is a prepared-data directory (new checksums, same ids, gold labels
and holdings) for `jev-bench run --max-chars 0`, plus per-task statistics in `context.json`
there and in the tracked `analysis/bertctx-context.json`.
"""

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

from tokenizers import Tokenizer

from jev_test.data import CATALOG
from jev_test.storage import read_jsonl

TOKENIZER_REPO = "google-bert/bert-base-uncased"
TOKENIZER_REVISION = "86b5e0934494bd15c9632b12f734a8a67f723594"
UPSTREAM_COMMIT = "419a49d0fe82ecb69eb8e9343a9eb3382f1040fd"
LIMITS = {"eurlex": 512, "ledgar": 512, "unfair_tos": 128}
SEGMENTS, SEGMENT_TOKENS, CASEHOLD_TOKENS = 64, 128, 256


def tokenizer() -> Tokenizer:
    cache = Path.home() / ".cache" / "jev-test" / f"bert-base-uncased-{TOKENIZER_REVISION}.json"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{TOKENIZER_REPO}/resolve/{TOKENIZER_REVISION}/tokenizer.json"
        cache.write_bytes(urllib.request.urlopen(url, timeout=60).read())
    return Tokenizer.from_file(str(cache))


def kept_end(tok: Tokenizer, text: str, limit: int, pair: str | None = None) -> int:
    """Character offset in `text` where the last kept word piece ends."""
    tok.enable_truncation(max_length=limit, strategy="longest_first")
    enc = tok.encode(text, pair) if pair is not None else tok.encode(text)
    ends = [end for (_, end), seq in zip(enc.offsets, enc.sequence_ids, strict=True) if seq == 0]
    end = max(ends, default=0)
    return len(text) if not text[end:].strip() else end  # only whitespace was left out


def segments_cut(tok: Tokenizer, segments: list[str]) -> str:
    return "\n\n".join(s[: kept_end(tok, s, SEGMENT_TOKENS)] for s in segments[:SEGMENTS])


def ecthr_paragraphs(task: str) -> list[list[str]]:
    import datasets

    url = f"hf://datasets/{CATALOG['dataset']}@{CATALOG['revision']}/{task}/test-*.parquet"
    rows = datasets.load_dataset("parquet", data_files={"test": url}, split="test")
    return rows["text"]


def cut(tok: Tokenizer, task: str, row: dict, paragraphs: list[str] | None) -> str:
    text = row["text"]
    if task.startswith("ecthr"):
        if "\n\n".join(paragraphs) != text:
            raise ValueError(f"{row['id']}: Parquet paragraphs do not rejoin to the prepared text")
        return segments_cut(tok, paragraphs)
    if task == "scotus":
        return segments_cut(tok, re.split("\n{2,}", text))
    if task == "case_hold":
        return text[: max(kept_end(tok, text, CASEHOLD_TOKENS, e) for e in row["endings"])]
    return text[: kept_end(tok, text, LIMITS[task])]


def main(source: Path, output: Path) -> None:
    tok = tokenizer()
    manifest = json.loads((source / "manifest.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    stats = {}
    for task, info in manifest["tasks"].items():
        rows = read_jsonl(source / info["file"])
        paragraphs = ecthr_paragraphs(task) if task.startswith("ecthr") else None
        lines, original, kept, shortened = [], 0, 0, 0
        for row in rows:
            text = cut(tok, task, row, paragraphs[row["index"]] if paragraphs else None)
            if not text.strip():
                raise ValueError(f"{row['id']}: nothing left after cutting")
            original += len(row["text"])
            kept += len(text)
            shortened += len(text) < len(row["text"])
            lines.append(json.dumps({**row, "text": text}) + "\n")
        path = output / info["file"]
        path.write_text("".join(lines))
        info["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        stats[task] = {
            "n": len(rows),
            "mean_original_chars": original / len(rows),
            "mean_kept_chars": kept / len(rows),
            "kept_fraction_of_chars": kept / original,
            "documents_shortened": shortened,
        }
        print(task, json.dumps(stats[task]), flush=True)
    manifest["derived"] = {
        "from": str(source),
        "transform": "BERT-matched context (bert/context_matched.py)",
        "tokenizer": f"{TOKENIZER_REPO}@{TOKENIZER_REVISION}",
        "upstream_lexglue_commit": UPSTREAM_COMMIT,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "context.json").write_text(json.dumps(stats, indent=2) + "\n")
    tracked = Path(__file__).resolve().parent.parent / "analysis" / "bertctx-context.json"
    tracked.write_text(json.dumps(stats, indent=2) + "\n")  # data/ is gitignored


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
