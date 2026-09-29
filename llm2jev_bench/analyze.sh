#!/usr/bin/env bash
# Paired analyses of LLM2Jev (Qwen3.5-4B) against Jev and Kev-4B from the run ledgers; no network.
set -eu
cd "$(dirname "$0")/.."
R=results
uv run jev-bench report $R/llm2jev-full
uv run jev-bench report $R/llm2jev-intents-test
uv run jev-bench analyze --source jev=$R/full-test/predictions.jsonl \
  --source llm2jev=$R/llm2jev-full/predictions.jsonl --output analysis/jev-vs-llm2jev.json
uv run jev-bench analyze --source kev4b=$R/kev4b-full/predictions.jsonl \
  --source llm2jev=$R/llm2jev-full/predictions.jsonl --output analysis/kev4b-vs-llm2jev.json
uv run python analysis/paired_auc.py $R/full-test/predictions.jsonl \
  $R/llm2jev-full/predictions.jsonl > analysis/paired-auc-llm2jev.json
uv run python analysis/paired_auc.py $R/kev4b-full/predictions.jsonl \
  $R/llm2jev-full/predictions.jsonl > analysis/paired-auc-kev4b-vs-llm2jev.json
uv run jev-bench analyze --source jev=$R/jev-intents-test/predictions.jsonl \
  --source llm2jev=$R/llm2jev-intents-test/predictions.jsonl --output analysis/intents-jev-vs-llm2jev.json
uv run jev-bench analyze --source kev4b=$R/kev4b-intents-test/predictions.jsonl \
  --source llm2jev=$R/llm2jev-intents-test/predictions.jsonl --output analysis/intents-kev4b-vs-llm2jev.json
uv run python llm2jev_bench/ties.py $R/llm2jev-full/predictions.jsonl > analysis/llm2jev-ties.json
uv run python kev_suites/summarize.py > analysis/kev-suites.md
