#!/usr/bin/env bash
# Paired analyses of the context, prompt and redraw controls (analysis/PREREG-controls.md).
#   scripts/control_analyses.sh jev     # J1 vs J0, JB vs J1 and BERT
#   scripts/control_analyses.sh luna    # L1 vs L0, LP vs L1, Jev vs L1 and LP
# Same bootstrap as every other comparison (jev_test.analysis.paired, 1,000 resamples, seed 0,
# ids sorted); each comparison uses the ids both ledgers scored.
set -euo pipefail
cd "$(dirname "$0")/.."
A() {
  local output=$1
  shift
  local args=()
  for s in "$@"; do args+=(--source "${s%%=*}=results/${s#*=}/predictions.jsonl"); done
  uv run --quiet jev-bench analyze "${args[@]}" --output "analysis/$output.tmp" > /dev/null
  mv "analysis/$output.tmp" "analysis/$output"
  echo "done $output"
}
case "${1:-all}" in
  jev | all)
    A control-jev-redraw.json jev_redraw=jev-redraw jev=full-test &
    A control-jev-context.json jev_bertctx=jev-bertctx jev_redraw=jev-redraw bert=bert-seed1 &
    wait
    ;;&
  luna | all)
    A control-luna-redraw.json luna_redraw=luna-redraw luna=luna-full &
    A control-luna-prompt.json luna_perlabel=luna-perlabel luna_redraw=luna-redraw &
    A control-jev-vs-luna-arms.json jev=full-test luna_redraw=luna-redraw luna_perlabel=luna-perlabel jev_redraw=jev-redraw &
    wait
    ;;
esac
