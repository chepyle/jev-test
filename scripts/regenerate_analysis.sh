#!/usr/bin/env bash
# Rebuild the ledger-derived files in analysis/ from results/*/predictions.jsonl; no network.
#
#   scripts/regenerate_analysis.sh                 # writes analysis/
#   OUT=/tmp/x JOBS=6 scripts/regenerate_analysis.sh
#   RESUME=1 scripts/regenerate_analysis.sh        # skip outputs that already exist
#
# Each output is written to a temporary file and renamed, so an interrupted run leaves no
# partial file and RESUME=1 picks up where it stopped. Scripts with their own fixed output
# (train probe, Kev suites, threshold tuning, decision index, refusal sensitivity,
# multiplicity, controls) are listed at the end and run after the bootstrap jobs.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${OUT:-analysis}
JOBS=${JOBS:-4}
RESUME=${RESUME:-0}
mkdir -p "$OUT"

jobs_list() {
  # analyze OUTPUT NAME=RUN [NAME=RUN ...]   |   auc OUTPUT RUN_A RUN_B
  cat <<'EOF'
analyze full-test.json jev=full-test
analyze intents-test.json jev=jev-intents-test
analyze jev-vs-bert.json jev=full-test bert=bert-seed1
analyze three-way.json jev=full-test luna=luna-full bert=bert-seed1
analyze luna-vs-bert.json luna=luna-full bert=bert-seed1
analyze sample50-jev-vs-luna.json jev=smoke50 luna=luna-smoke50
analyze jev-vs-kev4b.json jev=full-test kev4b=kev4b-full
analyze intents-jev-vs-kev4b.json jev=jev-intents-test kev4b=kev4b-intents-test
analyze jev-vs-llm2jev.json jev=full-test llm2jev=llm2jev-full
analyze kev4b-vs-llm2jev.json kev4b=kev4b-full llm2jev=llm2jev-full
analyze intents-jev-vs-llm2jev.json jev=jev-intents-test llm2jev=llm2jev-intents-test
analyze intents-kev4b-vs-llm2jev.json kev4b=kev4b-intents-test llm2jev=llm2jev-intents-test
analyze jev-vs-clef-flash.json jev=full-test clef_flash=clef-flash-full
analyze kev4b-vs-clef-flash.json kev4b=kev4b-full clef_flash=clef-flash-full
analyze intents-jev-vs-clef-flash.json jev=jev-intents-test clef_flash=clef-flash-intents-test
analyze intents-kev4b-vs-clef-flash.json kev4b=kev4b-intents-test clef_flash=clef-flash-intents-test
analyze jev-vs-elephant.json jev=full-test elephant=elephant-full
analyze kev4b-vs-elephant.json kev4b=kev4b-full elephant=elephant-full
analyze intents-jev-vs-elephant.json jev=jev-intents-test elephant=elephant-intents-test
analyze intents-kev4b-vs-elephant.json kev4b=kev4b-intents-test elephant=elephant-intents-test
analyze jev-vs-decisions-luna.json jev=full-test decisions=decisions-full luna-chat=luna-full
analyze lunachat-vs-decisions.json luna-chat=luna-full decisions=decisions-full
auc paired-auc.json full-test bert-seed1
auc paired-auc-kev4b.json full-test kev4b-full
auc paired-auc-llm2jev.json full-test llm2jev-full
auc paired-auc-kev4b-vs-llm2jev.json kev4b-full llm2jev-full
auc paired-auc-clef-flash.json full-test clef-flash-full
auc paired-auc-elephant.json full-test elephant-full
auc paired-auc-decisions.json full-test decisions-full
EOF
  if [ -n "${EXTRA_JOBS:-}" ]; then cat "$EXTRA_JOBS"; fi
}

one() {
  local kind=$1 output=$2
  shift 2
  local target="$OUT/$output"
  if [ "$RESUME" = 1 ] && [ -s "$target" ]; then
    echo "skip $output"
    return 0
  fi
  local tmp="$target.tmp.$$"
  if [ "$kind" = analyze ]; then
    local args=()
    for s in "$@"; do args+=(--source "${s%%=*}=results/${s#*=}/predictions.jsonl"); done
    uv run --quiet jev-bench analyze "${args[@]}" --output "$tmp" > /dev/null
  else
    uv run --quiet python analysis/paired_auc.py \
      "results/$1/predictions.jsonl" "results/$2/predictions.jsonl" > "$tmp"
  fi
  mv "$tmp" "$target"
  echo "done $output"
}
export -f one
export OUT RESUME

jobs_list | xargs -P "$JOBS" -L 1 bash -c 'one "$@"' _
