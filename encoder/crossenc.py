"""Cross-encoder framing of System One questions, shared by training, prediction and tests.

A System One question has its own option set (choice: named criteria; noul: false/true;
score: ordered levels), so no fixed label head fits every question. Each option becomes one
(input, question + option) pair; a scalar head scores every pair and a softmax over one
question's pairs gives its answer distribution. The same framing serves a fine-tuned
scorer (one logit per pair) and an NLI model (entailment minus not-entailment logit).

Only the request fields Kev sends to a remote model are used (kev.data.api_request: state,
type, instructions, criteria), never labels or metadata.
"""

import hashlib
import json

MAX_LENGTH = 512  # tokens per pair; Kev's suites admit states of at most 384 Qwen tokens


def render(value, indent: int = 0) -> str:
    """Kev's state rendering (kev.api.render): field names kept as labels."""
    pad = "  " * indent
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(f"{pad}- {render(x, indent + 1).lstrip()}" for x in value)
    return "\n".join(
        f"{pad}{k}:\n{render(x, indent + 1)}"
        if isinstance(x, (dict, list))
        else f"{pad}{k}: {render(x)}"
        for k, x in value.items()
    )


def api_request(record: dict) -> dict:
    """kev.data.api_request: what leaves the machine for a remote model."""
    return {
        "state": record["state"],
        "questions": {
            qid: {k: v for k, v in q.items() if k in ("type", "instructions", "criteria")}
            for qid, q in record["questions"].items()
        },
    }


def request_key(request: dict) -> str:
    """Hash of a System One request's state and questions (the model field is ignored)."""
    core = {"state": request["state"], "questions": request["questions"]}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def option_keys(question: dict) -> list[str]:
    """Answer keys as Kev names them: criteria (choice), false/true (noul), level index (score)."""
    if question["type"] == "choice":
        return list(question["criteria"])
    if question["type"] == "noul":
        return ["false", "true"]
    return [str(i) for i in range(len(question["criteria"]))]


def option_texts(question: dict) -> list[str]:
    criteria = question.get("criteria")
    if question["type"] == "choice":
        return [k if v in (None, "") else f"{k}: {render(v)}" for k, v in criteria.items()]
    if question["type"] == "noul":
        if criteria:
            return [
                f"{k}: {render(criteria.get(k))}" if criteria.get(k) else k
                for k in ("false", "true")
            ]
        return ["no", "yes"]
    return [f"level {i}: {render(v)}" for i, v in enumerate(criteria)]


def label_index(question: dict) -> int:
    """Gold option index from a labelled Kev record (training and selection only)."""
    label = question["label"]
    if question["type"] == "choice":
        return list(question["criteria"]).index(label)
    if question["type"] == "noul":
        return int(bool(label))
    return int(label)


def pairs(request: dict) -> list[tuple[str, str, list[str], list[tuple[str, str]]]]:
    """(qid, type, keys, [(input text, question + option text), ...]) for each question."""
    state = render(request["state"])
    out = []
    for qid, q in request["questions"].items():
        texts = option_texts(q)
        out.append(
            (qid, q["type"], option_keys(q), [(state, f"{q['instructions']}\n{t}") for t in texts])
        )
    return out


def to_answers(request: dict, probs: dict[str, list[float]], model: str) -> dict:
    """System One response body from per-question option probabilities."""
    answers = {}
    for qid, q in request["questions"].items():
        keys, p = option_keys(q), probs[qid]
        if q["type"] == "noul":
            answers[qid] = {"type": "noul", "noul": float(p[1])}
            continue
        best = max(range(len(p)), key=p.__getitem__)
        answers[qid] = {
            "type": q["type"],
            "choice": keys[best],
            "probabilities": {k: float(v) for k, v in zip(keys, p, strict=True)},
        }
    return {"model": model, "answers": answers}
