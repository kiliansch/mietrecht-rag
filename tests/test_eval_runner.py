from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from src import config
from src.eval import runner
from src.eval.runner import _hit_metrics, run_eval


def _doc(file_number: str) -> Document:
    return Document(page_content="…", metadata={"file_number": file_number})


def test_hit_metrics_empty_without_references():
    # Statutes-style items (no reference_file_number) contribute nothing.
    retrieved = [({"question": "q"}, [_doc("VIII ZR 1/20")])]
    assert _hit_metrics(retrieved) == {}


def test_hit_metrics_rank_and_hit_rate():
    retrieved = [
        # gold at rank 2 -> hit, rr = 1/2
        ({"reference_file_number": "VIII ZR 305/19"}, [_doc("X 1/1"), _doc("VIII ZR 305/19")]),
        # gold not retrieved -> miss, rr = 0
        ({"reference_file_number": "1 S 222/22"}, [_doc("X 2/2"), _doc("Y 3/3")]),
        # gold at rank 1 -> hit, rr = 1
        ({"reference_file_number": "4 C 111/22"}, [_doc("4 C 111/22")]),
    ]
    scores = _hit_metrics(retrieved)
    assert scores["hit_rate"] == round(2 / 3, 3)
    assert scores["mrr"] == round((0.5 + 0 + 1.0) / 3, 3)


def test_hit_metrics_substring_match_both_directions():
    # Stored file_number may carry extra tokens; match if either contains the other.
    retrieved = [({"reference_file_number": "VIII ZR 21/13"}, [_doc("BGH VIII ZR 21/13")])]
    assert _hit_metrics(retrieved)["hit_rate"] == 1.0


def test_run_eval_includes_usage_block(tmp_path):
    # Minimal dataset: one statute + one case-law item, no live LLM.
    dataset = [
        {
            "question": "q1",
            "answer": "a1",
            "ground_truth": "g1",
            "collection": config.STATUTES_COLLECTION,
            "is_hallucination_plant": False,
        },
        {
            "question": "q2",
            "answer": "a2",
            "ground_truth": "g2",
            "collection": config.CASE_LAW_COLLECTION,
            "is_hallucination_plant": False,
            "reference_file_number": "X 1/20",
        },
    ]
    fake_retriever = MagicMock()
    fake_retriever.invoke.return_value = [_doc("X 1/20")]
    with (
        patch.object(runner, "_run_agent_turn", return_value=("ans", ["ctx"])),
        patch.object(runner, "_ragas_score", return_value={"context_precision": 0.9}),
        patch("src.retrieval.hybrid.get_hybrid_retriever", return_value=fake_retriever),
    ):
        results = run_eval(dataset=dataset, output_path=tmp_path / "eval.json")

    assert set(results["usage"]) == {"input_tokens", "output_tokens", "cost_usd", "by_model"}
    # No live LLM ran, so the captured usage is zero — but the block must be present.
    assert results["usage"]["input_tokens"] == 0
    assert (tmp_path / "eval.json").exists()
