#!/usr/bin/env bash
# Paired analyses of Clef-flash against Jev, Kev-4B and LLM2Jev from the run ledgers; no network.
set -eu
cd "$(dirname "$0")/.."
R=results
uv run jev-bench report $R/clef-flash-full
uv run jev-bench report $R/clef-flash-intents-test
uv run jev-bench analyze --source jev=$R/full-test/predictions.jsonl \
  --source clef_flash=$R/clef-flash-full/predictions.jsonl --output analysis/jev-vs-clef-flash.json
uv run jev-bench analyze --source kev4b=$R/kev4b-full/predictions.jsonl \
  --source clef_flash=$R/clef-flash-full/predictions.jsonl --output analysis/kev4b-vs-clef-flash.json
uv run python analysis/paired_auc.py $R/full-test/predictions.jsonl \
  $R/clef-flash-full/predictions.jsonl > analysis/paired-auc-clef-flash.json
uv run jev-bench analyze --source jev=$R/jev-intents-test/predictions.jsonl \
  --source clef_flash=$R/clef-flash-intents-test/predictions.jsonl \
  --output analysis/intents-jev-vs-clef-flash.json
uv run jev-bench analyze --source kev4b=$R/kev4b-intents-test/predictions.jsonl \
  --source clef_flash=$R/clef-flash-intents-test/predictions.jsonl \
  --output analysis/intents-kev4b-vs-clef-flash.json
uv run python analysis/decision_index_check.py > analysis/decision-index-check.json
uv run python kev_suites/summarize.py > analysis/kev-suites.md
