"""Match the task metrics in coastalcph/lex-glue/experiments/*.py."""

import math
import statistics

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

from jev_test.tasks import get_task


def score(task_name: str, gold: list[list[int]], predictions: list[list[int]]) -> dict:
    task = get_task(task_name)
    if not gold or len(gold) != len(predictions):
        raise ValueError("Scoring requires nonempty, equally sized gold and prediction lists")
    for labels in gold + predictions:
        task.validate_labels(labels)
    if task.multilabel:
        width = len(task.codes) + int(task.has_none_class)
        truth = np.zeros((len(gold), width), dtype=int)
        predicted = np.zeros_like(truth)
        for matrix, rows in ((truth, gold), (predicted, predictions)):
            for index, labels in enumerate(rows):
                matrix[index, labels] = 1
                if task.has_none_class and not labels:
                    matrix[index, -1] = 1
    else:
        truth = np.array([labels[0] for labels in gold])
        predicted = np.array([labels[0] for labels in predictions])
    # As upstream: all columns for multilabel; observed label union for multiclass.
    return {
        "micro_f1": float(f1_score(truth, predicted, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(truth, predicted, average="macro", zero_division=0)),
        "exact_match": float(accuracy_score(truth, predicted)),
    }


def aggregate(task_scores: list[dict]) -> dict:
    result = {}
    for metric in ("micro_f1", "macro_f1"):
        values = [scores[metric] for scores in task_scores]
        result[metric] = {
            "arithmetic": statistics.mean(values),
            "harmonic": statistics.harmonic_mean(values),
            "geometric": 0.0 if 0 in values else math.exp(statistics.mean(map(math.log, values))),
        }
    return result
