"""Guards on the single evaluation dataset (see src/eval/dataset.py).

The case-law question count is asserted at >= 20 because the review flagged that
at n < 20 the case-law context-precision metric cannot distinguish a real
retrieval improvement from noise.
"""

from src import config
from src.eval.dataset import EVAL_DATASET

_REQUIRED_KEYS = {
    "question",
    "answer",
    "ground_truth",
    "is_hallucination_plant",
    "sections_needed",
    "collection",
    "notes",
}
_VALID_COLLECTIONS = {config.STATUTES_COLLECTION, config.CASE_LAW_COLLECTION}


def _by_collection(collection: str) -> list[dict]:
    return [item for item in EVAL_DATASET if item["collection"] == collection]


def test_case_law_set_is_statistically_meaningful():
    case_law = _by_collection(config.CASE_LAW_COLLECTION)
    assert len(case_law) >= 20, (
        f"case-law eval set has {len(case_law)} items; the review requires >= 20 "
        "so case-law context precision/recall are meaningful."
    )


def test_every_item_has_the_full_schema():
    for item in EVAL_DATASET:
        # Case-law items additionally carry a gold `reference_file_number` for the
        # deterministic hit-rate/MRR retrieval metrics.
        allowed = _REQUIRED_KEYS | {"reference_file_number"}
        assert _REQUIRED_KEYS <= set(item) <= allowed, item.get("question", "<no question>")
        assert item["collection"] in _VALID_COLLECTIONS
        assert isinstance(item["sections_needed"], list)
        assert item["question"] and item["ground_truth"]


def test_every_case_law_item_has_a_reference_file_number():
    for item in _by_collection(config.CASE_LAW_COLLECTION):
        assert item.get("reference_file_number"), item["question"]


def test_exactly_one_planted_hallucination():
    plants = [item for item in EVAL_DATASET if item["is_hallucination_plant"]]
    assert len(plants) == 1


def test_notes_carry_a_source_citation_for_case_law():
    # Each case-law item must name its grounding decision (court + file number) so
    # the eval set is auditable against the corpus.
    for item in _by_collection(config.CASE_LAW_COLLECTION):
        assert item["notes"].strip(), item["question"]
