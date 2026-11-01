"""OpenAI Decisions API protocol (`POST /v1/decisions`).

Same instructions, label descriptions, truncation, and gold isolation as the System One
protocol. Multi-label tasks ask one `predicate` question per label (the analogue of a
System One `noul`); single-label tasks ask one `choice` question. Answers carry
probabilities, so thresholding, ROC-AUC, and calibration apply.

Refusals: the API can return `{"type": "refusal", "name": ...}` for a single question; the docs
do not say when. A refused predicate is imputed as "label not applied" with probability 0.0
(an imputation: it biases ROC-AUC slightly and is counted from the raw responses). A refused
choice question is a failed example (Refusal): no label can be inferred, and the run
continues so the refusal rate is measured.
"""

import math

from jev_test.questions import INSTRUCTIONS, truncate
from jev_test.tasks import get_task

DECISIONS_PROTOCOL_VERSION = "lexglue-decisions-v1"
DECISIONS_ENDPOINT = "https://api.openai.com/v1/decisions"
DECISIONS_MODEL = "gpt-6-luna"


class Refusal(ValueError):
    """The API refused a choice question. Recorded as a failed example; the run continues."""


def build_decisions_request(row: dict, model: str, max_chars: int) -> tuple[dict, dict]:
    task = get_task(row["task"])
    text, truncated = truncate(row["text"], max_chars)
    instruction = INSTRUCTIONS[task.name]
    if task.multilabel:
        questions = [
            {
                "type": "predicate",
                "name": f"label_{index}",
                "instructions": f"{instruction} Does this label apply: {description}?",
            }
            for index, description in enumerate(task.descriptions)
        ]
    else:
        options = row["endings"] if task.name == "case_hold" else task.descriptions
        questions = [
            {
                "type": "choice",
                "name": "label",
                "instructions": instruction,
                "choices": [
                    {"value": str(i), "description": option} for i, option in enumerate(options)
                ],
            }
        ]
    payload = {"model": model, "input": text, "questions": questions}
    return payload, {
        "original_chars": len(row["text"]),
        "sent_chars": len(text),
        "truncated": truncated,
    }


def finite_probability(value: object, where: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{where}: probability must be finite and in [0, 1]")
    return value


def parse_decisions_response(
    task_name: str, response: dict, threshold: float
) -> tuple[list[int], dict]:
    """Strict parse: refusals, missing or extra answers raise instead of defaulting."""
    task = get_task(task_name)
    if not isinstance(response, dict) or not isinstance(response.get("answers"), list):
        raise ValueError("Decisions response is missing the answers array")
    if not isinstance(response.get("model"), str) or not response["model"]:
        raise ValueError("Decisions response is missing the resolved model ID")
    answers = {}
    for answer in response["answers"]:
        if not isinstance(answer, dict) or not isinstance(answer.get("name"), str):
            raise ValueError("Decisions answer is malformed")
        if answer["name"] in answers:
            raise ValueError(f"Duplicate answer {answer['name']}")
        answers[answer["name"]] = answer
    probabilities = {}
    if task.multilabel:
        if set(answers) != {f"label_{i}" for i in range(len(task.codes))}:
            raise ValueError("Decisions response has missing or unexpected label answers")
        for index in range(len(task.codes)):
            answer = answers[f"label_{index}"]
            if answer.get("type") == "refusal":
                probabilities[str(index)] = 0.0
                continue
            if answer.get("type") != "predicate":
                raise ValueError(f"label_{index}: expected a predicate answer (refusal?)")
            probabilities[str(index)] = finite_probability(
                answer.get("probability"), f"label_{index}"
            )
        return [int(i) for i, p in probabilities.items() if p > threshold], probabilities
    if set(answers) != {"label"}:
        raise ValueError("Expected exactly one choice answer named label")
    answer = answers["label"]
    if answer.get("type") == "refusal":
        raise Refusal("API refused the choice question")
    valid = {str(i) for i in range(len(task.codes))}
    if answer.get("type") != "choice" or answer.get("choice") not in valid:
        raise ValueError("Invalid choice; expected one of the supplied zero-based string keys")
    entries = answer.get("probabilities")
    if not isinstance(entries, list):
        raise ValueError("Choice answer is missing the probabilities array")
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("value") not in valid:
            raise ValueError("Choice probabilities contain an unknown option")
        probabilities[entry["value"]] = finite_probability(entry.get("probability"), "choice")
    return [int(answer["choice"])], probabilities
