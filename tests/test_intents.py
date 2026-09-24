import hashlib

import pytest

from jev_test import data
from jev_test.data import fetch_verified, normalize, prepare
from jev_test.questions import INSTRUCTIONS, build_request
from jev_test.tasks import ALL_TASKS, CATALOG, INTENT_TASKS, TASK_NAMES, catalog_for, get_task


def test_intent_tasks_are_a_separate_suite_and_lexglue_is_untouched():
    assert INTENT_TASKS == ("banking77", "clinc150")
    assert ALL_TASKS[: len(TASK_NAMES)] == TASK_NAMES
    assert catalog_for("ledgar") is CATALOG
    assert catalog_for("banking77")["dataset"] == "intent-detection"
    assert len(get_task("banking77").codes) == 77
    clinc = get_task("clinc150")
    assert len(clinc.codes) == 151 and "oos" in clinc.codes
    assert clinc.descriptions[clinc.codes.index("oos")].startswith("out of scope")
    assert all(name in INSTRUCTIONS for name in INTENT_TASKS)


def test_csv_string_labels_map_to_catalog_indices():
    row = normalize("banking77", 3, {"text": "Where is my card?", "category": "card_arrival"})
    assert row["gold"] == [get_task("banking77").codes.index("card_arrival")]
    assert row["id"] == "banking77/3"
    with pytest.raises(ValueError):
        normalize("banking77", 4, {"text": "hi", "category": "not_a_real_intent"})


def test_parquet_integer_labels_pass_through():
    row = normalize("clinc150", 0, {"text": "how would you say fly in italian", "intent": 61})
    assert row["gold"] == [61]


def test_request_offers_every_intent_and_never_the_gold_label():
    row = {"id": "clinc150/0", "task": "clinc150", "index": 0, "text": "set a timer", "gold": [32]}
    payload, _ = build_request(row, "m", 48_000)
    criteria = payload["questions"]["label"]["criteria"]
    assert len(criteria) == 151
    assert "gold" not in str(payload)


def test_mixing_suites_in_one_directory_is_refused(tmp_path):
    with pytest.raises(ValueError, match="one benchmark suite"):
        prepare(tmp_path / "out", ["ledgar", "banking77"], "test", 1, 42)


def test_pinned_source_is_refused_on_checksum_mismatch(tmp_path, monkeypatch):
    class Response:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(data.urllib.request, "urlopen", lambda *a, **k: Response(b"tampered"))
    with pytest.raises(ValueError, match="Checksum mismatch"):
        fetch_verified("https://example.org/test.csv", "0" * 64, tmp_path)
    good = hashlib.sha256(b"tampered").hexdigest()
    assert fetch_verified("https://example.org/test.csv", good, tmp_path) == b"tampered"
    assert (tmp_path / good).read_bytes() == b"tampered"
