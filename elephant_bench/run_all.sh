#!/usr/bin/env bash
# Intents, LexGLUE, then Kev's suites for elephant-1. Every stage resumes from its ledger, so
# re-running this script after an interruption continues where it stopped.
set -u
cd "$(dirname "$0")/.."
elephant_bench/run.sh elephant-intents data/intents-test results/elephant-intents-test || exit 1
elephant_bench/run.sh elephant-full data/full-test results/elephant-full || exit 1
kev_suites/run_elephant.sh
