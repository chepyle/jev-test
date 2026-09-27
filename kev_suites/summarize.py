"""Summarize Jev and Luna on Kev's frozen suites, next to Kev-4B's published reports.

Reads `results/kev-suites/<model>-<suite>-<split>/{report,rows}.json` written by
`kev.benchmark`, and Kev-4B's release/locked-test reports from `third_party/kev/runs`.
Point estimates are Kev's own (`report.json` "clean" block). Intervals: 95% bootstrap over
record groups (a contrastive pair resamples together), 1000 resamples, seed 0. Paired
differences use the same resampled groups for both models. Kev-4B has no public per-row
predictions, so it has point estimates only and no paired test.

    uv run python kev_suites/summarize.py > analysis/kev-suites.md
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "kev-suites"
KEV = ROOT / "third_party" / "kev"
MODELS = ("jev", "luna")
LABELS = {
    "jev": "Jev 1.13 (System One)",
    "luna": "GPT-5.6 Luna (chat JSON)",
    "kev-4b": "Kev-4B (published)",
}
SPLITS = [
    ("transfer-v4", "dev"),
    ("transfer-v4", "test"),
    ("decision-v7", "dev"),
    ("decision-v7", "test"),
]
RESAMPLES, SEED = 1000, 0


def clean_rows(model, suite, split):
    rows = json.loads((RESULTS / f"{model}-{suite}-{split}" / "rows.json").read_text())
    return {r["id"] + "/" + r["question"]: r for r in rows if r["variant"] == "clean"}


def correct(row):
    return int(np.argmax(row["p"]) == row["label"])


def bootstrap(groups, value, rng):
    """95% interval of `value(indices)` over resampled groups."""
    names = list(groups)
    stats = []
    for _ in range(RESAMPLES):
        pick = rng.integers(len(names), size=len(names))
        stats.append(value([i for g in pick for i in groups[names[g]]]))
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def kev4b_published():
    """Kev-4B r10 (the released checkpoint), as its README and model card cite them."""
    release = json.loads((KEV / "runs/release/kev-4b-r10.json").read_text())["candidate"]
    raw = json.loads((KEV / "runs/locked/kev-4b-r10-ungated/summary.json").read_text())["suites"]
    keys = {
        ("transfer-v4", "dev"): "transfer_dev",
        ("transfer-v4", "test"): "locked_transfer",
        ("decision-v7", "dev"): "decision_dev",
        ("decision-v7", "test"): "locked_decision",
    }
    out = {}
    for (suite, split), key in keys.items():
        block = release[key]
        entry = {
            "n": block["n"],
            "acc": block["acc"],
            "ece_calibrated": block["ece"],
            "brier_calibrated": block["brier"],
        }
        if split == "test":
            rawblock = raw["transfer" if suite == "transfer-v4" else "decision"]["clean"]
            entry.update(
                ece_raw=rawblock["ece"],
                brier_raw=rawblock["brier"],
                confident_error_rate_raw=rawblock["confident_error_rate"],
            )
        out[f"{suite}-{split}"] = entry
    return out


def main():
    rng = np.random.default_rng(SEED)
    summary = {
        "protocol": __doc__.split("\n\n")[1].replace("\n", " "),
        "splits": {},
        "kev-4b": kev4b_published(),
    }
    for suite, split in SPLITS:
        key = f"{suite}-{split}"
        rows = {m: clean_rows(m, suite, split) for m in MODELS}
        assert rows["jev"].keys() == rows["luna"].keys(), (
            f"{key}: models scored different questions"
        )
        ids = sorted(rows["jev"])
        groups = defaultdict(list)
        for i, qid in enumerate(ids):
            groups[rows["jev"][qid]["group"]].append(i)
        ok = {m: np.array([correct(rows[m][q]) for q in ids]) for m in MODELS}
        entry = {"n_questions": len(ids), "n_groups": len(groups), "models": {}}
        for m in MODELS:
            report = json.loads((RESULTS / f"{m}-{key}" / "report.json").read_text())
            clean = report["clean"]
            assert clean["n"] == len(ids) and abs(clean["acc"] - ok[m].mean()) < 1e-12, (
                f"{m} {key}: row/report mismatch"
            )
            entry["models"][m] = {
                "served_model": report["remote"]["served_model"],
                "coverage": report["coverage"],
                "acc": clean["acc"],
                "acc_ci": bootstrap(groups, lambda idx, hits=ok[m]: hits[idx].mean(), rng),
                "ece": clean["ece"],
                "brier": clean["brier"],
                "nll": clean["nll"],
                "confident_error_rate": clean["confident_error_rate"],
                "by_source": {
                    t: {"n": v["n"], "acc": v["acc"]} for t, v in sorted(report["tasks"].items())
                },
            }
        diff = ok["jev"] - ok["luna"]
        entry["jev_minus_luna"] = {
            "acc": float(diff.mean()),
            "ci": bootstrap(groups, lambda idx, diff=diff: diff[idx].mean(), rng),
        }
        summary["splits"][key] = entry
    (ROOT / "analysis" / "kev-suites.json").write_text(json.dumps(summary, indent=2) + "\n")
    print_tables(summary)


def fmt(ci):
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def print_tables(summary):
    kev = summary["kev-4b"]
    print(
        "| Split | n | Jev acc. [95% CI] | Luna acc. [95% CI] | Jev − Luna [95% CI] "
        "| Kev-4B acc. (published) |"
    )
    print("|---|---:|---|---|---|---:|")
    for key, e in summary["splits"].items():
        j, lu, d = e["models"]["jev"], e["models"]["luna"], e["jev_minus_luna"]
        print(
            f"| {key} | {e['n_questions']} | {j['acc']:.3f} {fmt(j['acc_ci'])} "
            f"| {lu['acc']:.3f} {fmt(lu['acc_ci'])} "
            f"| {d['acc']:+.3f} {fmt(d['ci'])} | {kev[key]['acc']:.3f} |"
        )
    print()
    print(
        "| Split | Jev ECE | Jev Brier | Jev confident errors "
        "| Kev-4B ECE raw / calibrated | Kev-4B Brier raw / calibrated |"
    )
    print("|---|---:|---:|---:|---|---|")
    for key, e in summary["splits"].items():
        j, k = e["models"]["jev"], kev[key]
        raw_ece = f"{k['ece_raw']:.3f}" if "ece_raw" in k else "–"
        raw_brier = f"{k['brier_raw']:.3f}" if "brier_raw" in k else "–"
        print(
            f"| {key} | {j['ece']:.3f} | {j['brier']:.3f} | {j['confident_error_rate']:.3f} "
            f"| {raw_ece} / {k['ece_calibrated']:.3f} | {raw_brier} / {k['brier_calibrated']:.3f} |"
        )
    print()
    for key in ("transfer-v4-test", "decision-v7-test"):
        e = summary["splits"][key]
        print(f"{key} accuracy by source:\n")
        print("| Source | n | Jev | Luna |")
        print("|---|---:|---:|---:|")
        for src, v in e["models"]["jev"]["by_source"].items():
            luna = e["models"]["luna"]["by_source"][src]["acc"]
            print(f"| {src} | {v['n']} | {v['acc']:.3f} | {luna:.3f} |")
        print()


if __name__ == "__main__":
    main()
