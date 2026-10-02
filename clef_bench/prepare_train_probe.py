"""Freeze 1,000 random training-split queries per intent dataset for the exposure probe.

    uv run python clef_bench/prepare_train_probe.py

`jev-bench prepare` offers only test and validation splits, which keeps training items out
of benchmark runs. This probe scores training items on purpose (see
PREREG-train-probe.md), so it calls the data layer directly with the same sampler.
"""

from pathlib import Path

from jev_test.data import prepare

if __name__ == "__main__":
    prepare(Path("data/intents-train-probe"), ["banking77", "clinc150"], "train", 1000, 42)
