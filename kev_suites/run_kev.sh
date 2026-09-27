#!/usr/bin/env bash
# Kev-4B (jaredpalmer/kev-4b served by Kev's own kev_modal.py on a Modal L40S) on Kev's frozen suites, scored by Kev's own kev.benchmark.
set -u
: "${KEV_URL:?set KEV_URL to the deployed endpoint}" "${KEV_API_KEY:?}"
cd "$(dirname "$0")/../third_party/kev"
OUT=../../results/kev-suites
export KEV_REMOTE_API_KEY=$KEV_API_KEY
for spec in "transfer-v4 evals/v4/transfer-v4 dev" "transfer-v4 evals/v4/transfer-v4 test" "decision-v7 evals/v7/decision-v7 dev" "decision-v7 evals/v7/decision-v7 test"; do
  set -- $spec; name=$1; suite=$2; split=$3
  dir=$OUT/kev4b-$name-$split
  [ -f "$dir/report.json" ] && { echo "skip $dir"; continue; }
  rm -rf "$dir"
  flag=""; [ "$split" = test ] && flag="--allow-test"
  echo "$(date -Is) start $dir"
  uv run python -m kev.benchmark --remote "$KEV_URL" --remote-model kev-latest \
    --remote-concurrency 8 --suite "$suite" $flag --out "$dir" > "$dir.log" 2>&1
  echo "$(date -Is) exit $? $dir"
done
