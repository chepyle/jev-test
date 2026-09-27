#!/usr/bin/env bash
# Jev (OpenRouter System One) on Kev's frozen suites, scored by Kev's own kev.benchmark.
set -u
cd "$(dirname "$0")/../third_party/kev"
OUT=../../results/kev-suites
export KEV_REMOTE_API_KEY=$OPENROUTER_API_KEY
for spec in "transfer-v4 evals/v4/transfer-v4 dev" "transfer-v4 evals/v4/transfer-v4 test" "decision-v7 evals/v7/decision-v7 dev" "decision-v7 evals/v7/decision-v7 test"; do
  set -- $spec; name=$1; suite=$2; split=$3
  dir=$OUT/jev-$name-$split
  [ -f "$dir/report.json" ] && { echo "skip $dir"; continue; }
  rm -rf "$dir"
  flag=""; [ "$split" = test ] && flag="--allow-test"
  echo "$(date -Is) start $dir"
  uv run python -m kev.benchmark --remote https://openrouter.ai/api --remote-model typesafe/jev-1.13 \
    --remote-concurrency 4 --suite "$suite" $flag --out "$dir" > "$dir.log" 2>&1
  echo "$(date -Is) exit $? $dir"
done
