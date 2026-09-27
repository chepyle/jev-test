"""Build report/findings.html from the committed analysis files.

    uv run python report/build_report.py

Every number in the page is read from analysis/*.json or the run ledgers under results/
(error examples and costs). The script asserts the headline means against the values
reported in RESULTS.md, so a drifted input fails loudly instead of shipping a wrong page.
"""

import collections
import json
from pathlib import Path

from jev_test.tasks import TASK_NAMES, get_task

ROOT = Path(__file__).resolve().parent.parent
TASK_LABELS = {
    "ecthr_a": "ECtHR A",
    "ecthr_b": "ECtHR B",
    "scotus": "SCOTUS",
    "eurlex": "EUR-LEX",
    "ledgar": "LEDGAR",
    "unfair_tos": "UNFAIR-ToS",
    "case_hold": "CaseHOLD",
}
MULTILABEL = ("ecthr_a", "ecthr_b", "eurlex", "unfair_tos")
PUBLISHED = {  # read from the papers' tables, see RESULTS.md
    "banking77": {"bert_full": 93.66, "bert_10shot": 83.42, "bert_30shot": 90.03},
    "clinc150": {"bert_in_scope": 96.7, "bert_oos_recall": 59.2, "best_oos_recall": 66.0},
}
COMMIT = "600c402"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def pct(x: float) -> float:
    return round(x * 100, 1)


def ledger(path: str) -> dict[str, dict]:
    last = {}
    for line in (ROOT / path).open():
        record = json.loads(line)
        last[record["id"]] = record
    return last


def top_confusions(records: dict, task: str, count: int) -> tuple[int, list]:
    codes = get_task(task).descriptions
    pairs = collections.Counter()
    errors = 0
    for r in records.values():
        if r["task"] == task and r["status"] == "ok" and r["gold"] != r["prediction"]:
            errors += 1
            pairs[(codes[r["gold"][0]], codes[r["prediction"][0]])] += 1
    return errors, [[g, p, n] for (g, p), n in pairs.most_common(count)]


def build() -> dict:
    three = load("analysis/three-way.json")
    kev = load("analysis/jev-vs-kev4b.json")
    kev_auc = load("analysis/paired-auc-kev4b.json")["tasks"]
    tuning = load("analysis/threshold-tuning.json")["tasks"]
    intents = load("analysis/intents-test.json")["sources"]["jev"]
    src = three["sources"]
    tasks = []
    for t in TASK_NAMES:
        row = {"task": t, "label": TASK_LABELS[t], "multilabel": t in MULTILABEL}
        for model in ("jev", "luna", "bert"):
            m = src[model][t]
            row[model] = {
                "micro": pct(m["metrics"]["micro_f1"]),
                "macro": pct(m["metrics"]["macro_f1"]),
                "ci": [pct(x) for x in m["ci95"]["micro_f1"]],
            }
        tuned = tuning[t]["test"]["per_label"] if t in tuning else None
        row["jev_tuned"] = (
            {"micro": pct(tuned["micro_f1"]), "macro": pct(tuned["macro_f1"])}
            if tuned
            else {"micro": row["jev"]["micro"], "macro": row["jev"]["macro"]}
        )
        vs_bert = three["paired"]["jev_vs_bert"][t]
        row["delta_bert"] = {
            "d": pct(vs_bert["delta_micro_f1"]),
            "ci": [pct(x) for x in vs_bert["delta_micro_f1_ci95"]],
            "p": vs_bert["mcnemar_exact_p"],
        }
        if t in tuning:
            d = tuning[t]["per_label_minus_baseline"]["micro_f1"]
            row["delta_bert_tuned"] = {"d": pct(d["delta"]), "ci": [pct(x) for x in d["ci95"]]}
        else:
            row["delta_bert_tuned"] = {"d": row["delta_bert"]["d"], "ci": row["delta_bert"]["ci"]}
        k = kev["sources"]["kev4b"][t]
        row["kev4b"] = {
            "micro": pct(k["metrics"]["micro_f1"]),
            "macro": pct(k["metrics"]["macro_f1"]),
            "ci": [pct(x) for x in k["ci95"]["micro_f1"]],
            "ece": round(k["metrics"]["ece"], 3),
        }
        row["jev"]["ece"] = round(src["jev"][t]["metrics"]["ece"], 3)
        vs_kev = kev["paired"]["jev_vs_kev4b"][t]
        row["delta_kev"] = {
            "d": pct(vs_kev["delta_micro_f1"]),
            "ci": [pct(x) for x in vs_kev["delta_micro_f1_ci95"]],
            "p": vs_kev["mcnemar_exact_p"],
            "only_jev": vs_kev["exact_correct_only_a"],
            "only_kev": vs_kev["exact_correct_only_b"],
        }
        if t in kev_auc:
            a = kev_auc[t]
            row["auc_kev"] = {
                "d": round(a["delta"], 3),
                "ci": [round(x, 3) for x in a["delta_ci95"]],
            }
        vs_luna = three["paired"]["jev_vs_luna"][t]
        row["delta_luna"] = {
            "d": pct(vs_luna["delta_micro_f1"]),
            "ci": [pct(x) for x in vs_luna["delta_micro_f1_ci95"]],
        }
        if t in tuning:
            row["thresholds"] = {
                "global": tuning[t]["chosen"]["global"],
                "default": {k: pct(v) for k, v in tuning[t]["test"]["default_0.5"].items()},
                "per_task": {k: pct(v) for k, v in tuning[t]["test"]["global"].items()},
                "per_label": {k: pct(v) for k, v in tuning[t]["test"]["per_label"].items()},
            }
        tasks.append(row)

    def mean(key: str, metric: str) -> float:
        return round(sum(r[key][metric] for r in tasks) / len(tasks), 1)

    means = {
        k: {"micro": mean(k, "micro"), "macro": mean(k, "macro")}
        for k in ("jev", "jev_tuned", "luna", "bert", "kev4b")
    }
    expected = {"jev": 69.9, "jev_tuned": 74.2, "luna": 71.3, "bert": 77.4, "kev4b": 62.1}
    for k, v in expected.items():  # RESULTS.md means are computed from unrounded scores
        assert abs(means[k]["micro"] - v) <= 0.1, (k, means[k]["micro"], v)

    jev_ledger = ledger("results/full-test/predictions.jsonl")
    intent_ledger = ledger("results/jev-intents-test/predictions.jsonl")
    ledgar_errors, ledgar_pairs = top_confusions(jev_ledger, "ledgar", 5)
    banking_errors, banking_pairs = top_confusions(intent_ledger, "banking77", 4)
    texts = {
        json.loads(line)["id"]: json.loads(line)["text"]
        for line in (ROOT / "data/intents-test/banking77.jsonl").open()
    }
    codes = get_task("banking77").codes
    pin_examples = [
        texts[r["id"]]
        for r in intent_ledger.values()
        if r["task"] == "banking77"
        and codes[r["gold"][0]] == "get_physical_card"
        and codes[r["prediction"][0]] == "change_pin"
    ][:3]

    def cost(path: str) -> float:
        return round(load(path)["usage"]["reported_cost_usd"], 2)

    b77, clinc = intents["banking77"], intents["clinc150"]
    kev_intents = load("analysis/intents-jev-vs-kev4b.json")
    kb77, kclinc = (kev_intents["sources"]["kev4b"][t] for t in ("banking77", "clinc150"))
    kev_pairs = kev_intents["paired"]["jev_vs_kev4b"]
    suites = load("analysis/kev-suites.json")
    kev_suites = []
    for key, e in suites["splits"].items():
        suite, split = key.rsplit("-", 1)
        kev_suites.append(
            {
                "key": key,
                "label": f"{suite} {split}",
                "held_out": suite == "transfer-v4",
                "n": e["n_questions"],
                "acc": {m: round(e["models"][m]["acc"] * 100, 1) for m in ("jev", "luna", "kev4b")},
                "ece": {m: round(e["models"][m]["ece"], 3) for m in ("jev", "kev4b")},
                **{
                    f"vs_{m}": {
                        "d": round(e[f"jev_minus_{m}"]["acc"] * 100, 1),
                        "ci": [round(x * 100, 1) for x in e[f"jev_minus_{m}"]["ci"]],
                    }
                    for m in ("luna", "kev4b")
                },
            }
        )
    kev_block = {
        "suites": kev_suites,
        "intents": {
            "banking77": {
                "acc": pct(kb77["metrics"]["accuracy"]),
                "ece": round(kb77["metrics"]["ece"], 3),
                "conf": pct(kb77["metrics"]["mean_confidence"]),
                "d": pct(kev_pairs["banking77"]["delta_micro_f1"]),
                "ci": [pct(x) for x in kev_pairs["banking77"]["delta_micro_f1_ci95"]],
            },
            "clinc150": {
                "acc": pct(kclinc["metrics"]["accuracy"]),
                "in_scope": pct(kclinc["metrics"]["in_scope_accuracy"]),
                "oos_recall": pct(kclinc["metrics"]["oos_recall"]),
                "ece": round(kclinc["metrics"]["ece"], 3),
                "conf": pct(kclinc["metrics"]["mean_confidence"]),
                "d": pct(kev_pairs["clinc150"]["delta_micro_f1"]),
                "ci": [pct(x) for x in kev_pairs["clinc150"]["delta_micro_f1_ci95"]],
            },
        },
        "confidence": {
            t: {
                "acc": pct(kev["sources"]["kev4b"][t]["metrics"]["accuracy"]),
                "conf": pct(kev["sources"]["kev4b"][t]["metrics"]["mean_confidence"]),
            }
            for t in ("scotus", "ledgar", "case_hold")
        },
    }
    return {
        "commit": COMMIT,
        "tasks": tasks,
        "means": means,
        "costs": {
            "jev": cost("results/full-test/metrics.json"),
            "luna": cost("results/luna-full/metrics.json"),
            "jev_validation": cost("results/jev-val-multilabel/metrics.json"),
            "intents": cost("results/jev-intents-test/metrics.json"),
            "bert_gpu": 21.58,
            "kev_gpu": 8.01,  # Modal billing report for app jev-test-kev, see RESULTS.md
            "kev_suites_openrouter": 0.42,
        },
        "kev": kev_block,
        "confusions": {
            "ledgar": {"errors": ledgar_errors, "pairs": ledgar_pairs},
            "banking77": {"errors": banking_errors, "pairs": banking_pairs},
            "pin_examples": pin_examples,
        },
        "intents": {
            "banking77": {
                "n": b77["n"],
                "acc": pct(b77["metrics"]["accuracy"]),
                "ci": [pct(x) for x in b77["ci95"]["micro_f1"]],
                "ece": round(b77["metrics"]["ece"], 3),
                **PUBLISHED["banking77"],
            },
            "clinc150": {
                "n": clinc["n"],
                "in_scope": pct(clinc["metrics"]["in_scope_accuracy"]),
                "in_scope_ci": [pct(x) for x in clinc["ci95"]["in_scope_accuracy"]],
                "oos_recall": pct(clinc["metrics"]["oos_recall"]),
                "oos_ci": [pct(x) for x in clinc["ci95"]["oos_recall"]],
                "oos_precision": pct(clinc["metrics"]["oos_precision"]),
                "acc": pct(clinc["metrics"]["accuracy"]),
                "ece": round(clinc["metrics"]["ece"], 3),
                **PUBLISHED["clinc150"],
            },
        },
    }


def main() -> None:
    data = build()
    template = (ROOT / "report" / "template.html").read_text()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = ROOT / "report" / "findings.html"
    out.write_text(template.replace("/*__DATA__*/null", payload))
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    print("means", data["means"])


if __name__ == "__main__":
    main()
