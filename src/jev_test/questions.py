"""Zero-shot System One questions. Gold answers never enter the request."""

import math

from jev_test.tasks import get_task

PROTOCOL_VERSION = "lexglue-systemone-v1"
INSTRUCTIONS = {
    "ecthr_a": "Using the facts of this European Court of Human Rights case, predict which "
    "Convention provisions the court found to have been violated.",
    "ecthr_b": "Using the facts of this European Court of Human Rights case, identify which "
    "Convention provisions were allegedly violated and considered by the court. "
    "An allegation counts even if the court ultimately found no violation.",
    "scotus": "Classify this US Supreme Court opinion by the main issue area of the dispute.",
    "eurlex": "Classify this European Union legal document by its EuroVoc subject concepts. "
    "Several concepts may apply independently.",
    "ledgar": "Select the single main topic of this contractual provision.",
    "unfair_tos": "Identify potentially unfair contractual terms in this terms-of-service "
    "sentence under European consumer law. Select a category only if the "
    "sentence is potentially unfair in that respect; a neutral mention is insufficient.",
    "case_hold": "Select the holding that correctly fills the masked citation in this court "
    "opinion excerpt. Exactly one of the five candidate holdings is correct.",
}


def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars < 0 or 0 < max_chars < 100:
        raise ValueError("max_chars must be 0 (unlimited) or at least 100")
    if not max_chars or len(text) <= max_chars:
        return text, False
    marker = "\n\n[... middle omitted by benchmark ...]\n\n"
    available = max_chars - len(marker)
    head = (available + 1) // 2
    tail = available - head
    return text[:head] + marker + text[-tail:], True


def build_request(row: dict, model: str, max_chars: int) -> tuple[dict, dict]:
    task = get_task(row["task"])
    text, truncated = truncate(row["text"], max_chars)
    instruction = INSTRUCTIONS[task.name]
    if task.multilabel:
        questions = {
            f"label_{index}": {
                "type": "noul",
                "instructions": f"{instruction} Does this label apply: {description}?",
                "criteria": {
                    "true": f"The label '{description}' applies to this document.",
                    "false": f"The label '{description}' does not apply to this document.",
                },
            }
            for index, description in enumerate(task.descriptions)
        }
    else:
        options = row["endings"] if task.name == "case_hold" else task.descriptions
        questions = {
            "label": {
                "type": "choice",
                "instructions": instruction,
                "criteria": {str(i): option for i, option in enumerate(options)},
            }
        }
    payload = {"model": model, "state": {"document": text}, "questions": questions}
    return payload, {
        "original_chars": len(row["text"]),
        "sent_chars": len(text),
        "truncated": truncated,
    }


def parse_response(task_name: str, response: dict, threshold: float) -> tuple[list[int], dict]:
    task = get_task(task_name)
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise ValueError("System One response is missing the answers object")
    if not isinstance(response.get("model"), str) or not response["model"]:
        raise ValueError("System One response is missing the resolved model ID")
    answers = response["answers"]
    probabilities = {}
    if task.multilabel:
        expected = {f"label_{i}" for i in range(len(task.codes))}
        if set(answers) != expected:
            raise ValueError("System One response has missing or unexpected label answers")
        for index in range(len(task.codes)):
            answer = answers[f"label_{index}"]
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise ValueError(f"label_{index}: expected a noul answer")
            value = answer.get("noul")
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"label_{index}: probability must be finite and in [0, 1]")
            probabilities[str(index)] = value
        return [int(i) for i, value in probabilities.items() if value > threshold], probabilities
    if set(answers) != {"label"} or not isinstance(answers["label"], dict):
        raise ValueError("Expected exactly one choice answer named label")
    answer = answers["label"]
    if (
        answer.get("type") != "choice"
        or not isinstance(answer.get("choice"), str)
        or answer["choice"] not in {str(i) for i in range(len(task.codes))}
    ):
        raise ValueError("Invalid choice; expected one of the supplied zero-based string keys")
    return [int(answer["choice"])], answer.get("probabilities", {})
