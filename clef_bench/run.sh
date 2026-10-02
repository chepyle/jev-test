#!/usr/bin/env bash
# Score a prepared jev-bench dataset against the deployed Clef-flash endpoint, resumably,
# under jobs/launch.py. Re-running the same command resumes from the ledger.
# Usage: clef_bench/run.sh <job-id> <data-dir> <output-dir> [concurrency]
set -eu
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export OPENROUTER_API_KEY=$LLM2JEV_API_KEY  # jev-bench sends this as the bearer key
URL=https://jakealbrecht--jev-test-clef-flash-server-api.modal.run/v1/systemone
exec uv run python jobs/launch.py "$1" "$2" "$3" --model clef-flash --endpoint "$URL" \
  --concurrency "${4:-16}" --timeout 600
