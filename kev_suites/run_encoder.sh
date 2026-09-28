#!/usr/bin/env bash
# A cross-encoder (encoder/modal_app.py logits) on Kev's frozen suites, scored by Kev's own kev.benchmark
# through encoder/replay.py, which fits the temperature on decision-v7 calibration and serves the stored logits.
# Usage: kev_suites/run_encoder.sh <name> [port]   (logits in results/kev-encoder/<name>/logits.jsonl)
set -u
name=$1; port=${2:-8766}
root="$(cd "$(dirname "$0")/.." && pwd)"
uv run --project "$root" python "$root/encoder/replay.py" "$root/results/kev-encoder/$name/logits.jsonl" \
  --port "$port" --model "$name" > "$root/results/kev-encoder/$name/replay.log" 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null' EXIT
until grep -q serving "$root/results/kev-encoder/$name/replay.log"; do
  kill -0 "$server" 2>/dev/null || { cat "$root/results/kev-encoder/$name/replay.log"; exit 1; }
  sleep 1
done
cd "$root/third_party/kev"
OUT=../../results/kev-suites
export KEV_REMOTE_API_KEY=local
for spec in "transfer-v4 evals/v4/transfer-v4 dev" "transfer-v4 evals/v4/transfer-v4 test" "decision-v7 evals/v7/decision-v7 dev" "decision-v7 evals/v7/decision-v7 test"; do
  set -- $spec; suite=$1; path=$2; split=$3
  dir=$OUT/$name-$suite-$split
  [ -f "$dir/report.json" ] && { echo "skip $dir"; continue; }
  rm -rf "$dir"
  flag=""; [ "$split" = test ] && flag="--allow-test"
  echo "$(date -Is) start $dir"
  uv run python -m kev.benchmark --remote "http://127.0.0.1:$port" --remote-model "$name" \
    --remote-concurrency 8 --suite "$path" $flag --out "$dir" > "$dir.log" 2>&1
  echo "$(date -Is) exit $? $dir"
done
