#!/usr/bin/env bash
# GPT-5.6 Luna (chat JSON via the local shim, python -m jev_test.chatshim on :8765) on Kev's frozen suites,
# scored by Kev's own kev.benchmark. The shim holds the OpenRouter key and caches every answer.
set -u
cd "$(dirname "$0")/../third_party/kev"
OUT=../../results/kev-suites
export KEV_REMOTE_API_KEY=local
for spec in "transfer-v4 evals/v4/transfer-v4 dev" "transfer-v4 evals/v4/transfer-v4 test" "decision-v7 evals/v7/decision-v7 dev" "decision-v7 evals/v7/decision-v7 test"; do
  set -- $spec; name=$1; suite=$2; split=$3
  dir=$OUT/luna-$name-$split
  [ -f "$dir/report.json" ] && { echo "skip $dir"; continue; }
  rm -rf "$dir"
  flag=""; [ "$split" = test ] && flag="--allow-test"
  echo "$(date -Is) start $dir"
  uv run python -m kev.benchmark --remote http://127.0.0.1:8765 --remote-model openai/gpt-5.6-luna \
    --remote-concurrency 8 --suite "$suite" $flag --out "$dir" > "$dir.log" 2>&1
  echo "$(date -Is) exit $? $dir"
done
