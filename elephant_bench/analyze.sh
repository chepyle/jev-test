#!/usr/bin/env bash
# Paired analyses of elephant-1 against Jev and Kev-4B from the run ledgers; no network.
set -eu
cd "$(dirname "$0")/.."
R=results
uv run jev-bench report $R/elephant-full
uv run jev-bench report $R/elephant-intents-test
uv run jev-bench analyze --source jev=$R/full-test/predictions.jsonl \
  --source elephant=$R/elephant-full/predictions.jsonl --output analysis/jev-vs-elephant.json
uv run jev-bench analyze --source kev4b=$R/kev4b-full/predictions.jsonl \
  --source elephant=$R/elephant-full/predictions.jsonl --output analysis/kev4b-vs-elephant.json
uv run python analysis/paired_auc.py $R/full-test/predictions.jsonl \
  $R/elephant-full/predictions.jsonl > analysis/paired-auc-elephant.json
uv run jev-bench analyze --source jev=$R/jev-intents-test/predictions.jsonl \
  --source elephant=$R/elephant-intents-test/predictions.jsonl \
  --output analysis/intents-jev-vs-elephant.json
uv run jev-bench analyze --source kev4b=$R/kev4b-intents-test/predictions.jsonl \
  --source elephant=$R/elephant-intents-test/predictions.jsonl \
  --output analysis/intents-kev4b-vs-elephant.json
