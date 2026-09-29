#!/usr/bin/env bash
# LLM2Jev (Qwen3.5-4B behind llm2jev_bench/modal_app.py on Modal) on Kev's frozen suites, scored by Kev's own kev.benchmark.
set -u
: "${LLM2JEV_URL:?set LLM2JEV_URL to the deployed endpoint}" "${LLM2JEV_API_KEY:?}"
cd "$(dirname "$0")/../third_party/kev"
OUT=../../results/kev-suites
export KEV_REMOTE_API_KEY=$LLM2JEV_API_KEY
for spec in "transfer-v4 evals/v4/transfer-v4 dev" "transfer-v4 evals/v4/transfer-v4 test" "decision-v7 evals/v7/decision-v7 dev" "decision-v7 evals/v7/decision-v7 test"; do
  set -- $spec; name=$1; suite=$2; split=$3
  dir=$OUT/llm2jev-$name-$split
  [ -f "$dir/report.json" ] && { echo "skip $dir"; continue; }
  rm -rf "$dir"
  flag=""; [ "$split" = test ] && flag="--allow-test"
  echo "$(date -Is) start $dir"
  uv run python -m kev.benchmark --remote "$LLM2JEV_URL" --remote-model qwen3.5-4b \
    --remote-concurrency 8 --suite "$suite" $flag --out "$dir" > "$dir.log" 2>&1
  echo "$(date -Is) exit $? $dir"
done
