#!/usr/bin/env bash
# Score a prepared jev-bench dataset against the deployed elephant-1 endpoint, resumably,
# under jobs/launch.py. Re-running the same command resumes from the ledger.
# Usage: elephant_bench/run.sh <job-id> <data-dir> <output-dir> [concurrency]
set -eu
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export OPENROUTER_API_KEY=$LLM2JEV_API_KEY  # jev-bench sends this as the bearer key
URL=https://jakealbrecht--jev-test-elephant-server-api.modal.run/v1/systemone
exec uv run python jobs/launch.py "$1" "$2" "$3" --model elephant-1 --endpoint "$URL" \
  --concurrency "${4:-16}" --timeout 600
