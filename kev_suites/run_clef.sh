#!/usr/bin/env bash
# Clef-flash (Cloudflare/clef-flash behind clef_bench/modal_app.py on Modal) on Kev's frozen suites, scored by Kev's own kev.benchmark.
set -u
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
URL=https://jakealbrecht--jev-test-clef-flash-server-api.modal.run
cd third_party/kev
OUT=../../results/kev-suites
export KEV_REMOTE_API_KEY=$LLM2JEV_API_KEY  # the endpoint reuses the llm2jev-serve-key secret
for spec in "transfer-v4 evals/v4/transfer-v4 dev" "transfer-v4 evals/v4/transfer-v4 test" "decision-v7 evals/v7/decision-v7 dev" "decision-v7 evals/v7/decision-v7 test"; do
  set -- $spec; name=$1; suite=$2; split=$3
  dir=$OUT/clef-flash-$name-$split
  [ -f "$dir/report.json" ] && { echo "skip $dir"; continue; }
  rm -rf "$dir"
  flag=""; [ "$split" = test ] && flag="--allow-test"
  echo "$(date -Is) start $dir"
  uv run python -m kev.benchmark --remote "$URL" --remote-model clef-flash \
    --remote-concurrency 8 --suite "$suite" $flag --out "$dir" > "$dir.log" 2>&1
  echo "$(date -Is) exit $? $dir"
done
