"""Task definitions and the pinned, zero-based Hugging Face label order."""

import json
from dataclasses import dataclass
from importlib.resources import files

CATALOG = json.loads(files("jev_test").joinpath("assets/labels.json").read_text())
DATASET_ID = CATALOG["dataset"]
DATASET_REVISION = CATALOG["revision"]
TASK_NAMES = ("ecthr_a", "ecthr_b", "scotus", "eurlex", "ledgar", "unfair_tos", "case_hold")


@dataclass(frozen=True)
class Task:
    name: str
    kind: str
    codes: tuple[str, ...]
    descriptions: tuple[str, ...]

    @property
    def multilabel(self) -> bool:
        return self.kind == "multilabel"

    @property
    def has_none_class(self) -> bool:
        return self.name in {"ecthr_a", "ecthr_b", "unfair_tos"}

    def validate_labels(self, labels: object) -> list[int]:
        if not isinstance(labels, list) or any(
            type(label) is not int or not 0 <= label < len(self.codes) for label in labels
        ):
            raise ValueError(f"{self.name}: labels must be a list of valid zero-based integers")
        if len(set(labels)) != len(labels) or (not self.multilabel and len(labels) != 1):
            raise ValueError(f"{self.name}: invalid number of labels or duplicate labels")
        return sorted(labels)


def get_task(name: str) -> Task:
    entry = CATALOG["tasks"][name]
    return Task(name, entry["kind"], tuple(entry["codes"]), tuple(entry["descriptions"]))
