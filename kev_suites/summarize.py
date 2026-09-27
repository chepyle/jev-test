"""Summarize Jev, Luna and Kev-4B on Kev's frozen suites.

Reads `results/kev-suites/<model>-<suite>-<split>/{report,rows}.json` written by
`kev.benchmark`, and Kev-4B's published release/locked-test reports from
`third_party/kev/runs` as a check on our served Kev-4B. Point estimates are Kev's own
(`report.json` "clean" block). Intervals: 95% bootstrap over record groups (a contrastive
pair resamples together), 1000 resamples, seed 0. Paired differences use the same
resampled groups for both models.

    uv run python kev_suites/summarize.py > analysis/kev-suites.md
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "kev-suites"
KEV = ROOT / "third_party" / "kev"
MODELS = ("jev", "luna", "kev4b")
LABELS = {
    "jev": "Jev 1.13 (System One)",
    "luna": "GPT-5.6 Luna (chat JSON)",
    "kev4b": "Kev-4B (served, temperature-scaled)",
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


def bootstrap(groups, value):
    """95% interval of `value(indices)` over resampled groups. Every call on a split draws the
    same resamples (fresh generator, fixed seed), so intervals do not depend on call order."""
    rng = np.random.default_rng(SEED)
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
    summary = {
        "protocol": __doc__.split("\n\n")[1].replace("\n", " "),
        "splits": {},
        "kev-4b": kev4b_published(),
    }
    for suite, split in SPLITS:
        key = f"{suite}-{split}"
        rows = {m: clean_rows(m, suite, split) for m in MODELS}
        for m in MODELS:
            assert rows[m].keys() == rows["jev"].keys(), f"{key}: {m} scored other questions"
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
                "acc_ci": bootstrap(groups, lambda idx, hits=ok[m]: hits[idx].mean()),
                "ece": clean["ece"],
                "brier": clean["brier"],
                "nll": clean["nll"],
                "confident_error_rate": clean["confident_error_rate"],
                "by_source": {
                    t: {"n": v["n"], "acc": v["acc"]} for t, v in sorted(report["tasks"].items())
                },
            }
        for other in ("luna", "kev4b"):
            diff = ok["jev"] - ok[other]
            entry[f"jev_minus_{other}"] = {
                "acc": float(diff.mean()),
                "ci": bootstrap(groups, lambda idx, diff=diff: diff[idx].mean()),
            }
        summary["splits"][key] = entry
    (ROOT / "analysis" / "kev-suites.json").write_text(json.dumps(summary, indent=2) + "\n")
    print_tables(summary)


def fmt(ci):
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def print_tables(summary):
    published = summary["kev-4b"]
    print(
        "| Split | n | Jev [95% CI] | Luna [95% CI] | Kev-4B [95% CI] "
        "| Jev − Luna [95% CI] | Jev − Kev-4B [95% CI] | Kev-4B published |"
    )
    print("|---|---:|---|---|---|---|---|---:|")
    for key, e in summary["splits"].items():
        m = e["models"]
        cells = " | ".join(f"{m[x]['acc']:.3f} {fmt(m[x]['acc_ci'])}" for x in MODELS)
        diffs = " | ".join(
            f"{e[f'jev_minus_{x}']['acc']:+.3f} {fmt(e[f'jev_minus_{x}']['ci'])}"
            for x in ("luna", "kev4b")
        )
        print(f"| {key} | {e['n_questions']} | {cells} | {diffs} | {published[key]['acc']:.3f} |")
    print()
    print(
        "| Split | Jev ECE / Brier / wrong at ≥0.9 | Kev-4B ECE / Brier / wrong at ≥0.9 "
        "| Kev-4B published ECE raw / scaled |"
    )
    print("|---|---|---|---|")
    for key, e in summary["splits"].items():
        j, k, p = e["models"]["jev"], e["models"]["kev4b"], published[key]
        raw = f"{p['ece_raw']:.3f}" if "ece_raw" in p else "–"
        print(
            f"| {key} | {j['ece']:.3f} / {j['brier']:.3f} / {j['confident_error_rate']:.3f} "
            f"| {k['ece']:.3f} / {k['brier']:.3f} / {k['confident_error_rate']:.3f} "
            f"| {raw} / {p['ece_calibrated']:.3f} |"
        )
    print()
    for key in ("transfer-v4-test", "decision-v7-test"):
        e = summary["splits"][key]
        print(f"{key} accuracy by source:\n")
        print("| Source | n | Jev | Luna | Kev-4B |")
        print("|---|---:|---:|---:|---:|")
        for src, v in e["models"]["jev"]["by_source"].items():
            accs = " | ".join(f"{e['models'][x]['by_source'][src]['acc']:.3f}" for x in MODELS)
            print(f"| {src} | {v['n']} | {accs} |")
        print()


if __name__ == "__main__":
    main()
