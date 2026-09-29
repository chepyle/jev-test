import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "llm2jev_bench"))

import compare_configs  # noqa: E402
import ties  # noqa: E402

CHOICE = {"type": "choice", "choice": "1", "confidence": 0.2, "probabilities": {"0": 0.4, "1": 0.6}}


def test_flatten_keys_choice_options_and_nouls():
    response = {"answers": {"label": CHOICE, "label_3": {"type": "noul", "noul": 0.5}}}
    assert compare_configs.flatten(response) == {"label/0": 0.4, "label/1": 0.6, "label_3": 0.5}


def test_decisions_treat_a_tie_as_not_applying():
    response = {"answers": {"label": CHOICE, "a": {"type": "noul", "noul": 0.5}}}
    assert compare_configs.decisions(response) == {"label": "1", "a": False}


def test_ties_counts_exact_half_on_multilabel_tasks_only(tmp_path):
    def row(id, task, status, gold, probabilities):
        return {
            "id": id,
            "task": task,
            "status": status,
            "gold": gold,
            "probabilities": probabilities,
        }

    rows = [
        row("e1", "ecthr_a", "ok", [0], {"0": 0.5, "1": 0.5, "2": 0.9}),
        row("e2", "ecthr_a", "error", [1], {"1": 0.5}),
        row("s1", "scotus", "ok", [0], {"0": 0.5, "1": 0.5}),
    ]
    path = tmp_path / "predictions.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert ties.main(path) == {
        "ecthr_a": {"decisions": 3, "ties": 2, "ties_gold_positive": 1, "tie_rate": 2 / 3}
    }
