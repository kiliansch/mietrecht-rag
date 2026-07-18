from unittest.mock import MagicMock, patch

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.retrieval.hybrid import (
    _CaseLawInnerRetriever,
    _ParentExpandingRetriever,
    _RerankingRetriever,
    _StatutesRetriever,
    _case_law_ensemble,
    _expand_queries,
    _extract_court_filter,
    _extract_section_filter,
    _rerank,
)


def _docs(*texts: str) -> list[Document]:
    return [Document(page_content=t) for t in texts]


def _child(text: str, parent_id: str | None) -> Document:
    meta = {"parent_id": parent_id} if parent_id is not None else {}
    return Document(page_content=text, metadata=meta)


class _FakeRetriever(BaseRetriever):
    """Minimal `BaseRetriever` stub returning a fixed list of docs."""

    docs: list[Document]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self.docs


def test_extract_section_filter_matches_plain_section():
    assert _extract_section_filter("Wie hoch darf die Kaution nach § 551 sein?") == {
        "section": "§ 551"
    }


def test_extract_section_filter_matches_lettered_suffix():
    assert _extract_section_filter("§555d Abs. 1 BGB Modernisierung") == {"section": "§ 555d"}


def test_extract_section_filter_matches_with_absatz_text():
    assert _extract_section_filter("Frist nach §558b Abs. 2 BGB") == {"section": "§ 558b"}


def test_extract_section_filter_none_without_citation():
    assert _extract_section_filter("Wann darf der Vermieter kündigen?") is None


def test_rerank_reorders_by_response_index():
    docs = _docs("irrelevant", "relevant", "somewhat relevant")
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "results": [
            {"index": 1, "relevance_score": 0.9},
            {"index": 2, "relevance_score": 0.5},
        ]
    }
    with patch("src.retrieval.hybrid.requests.post", return_value=fake_response) as post:
        result = _rerank("query", docs, top_n=2)

    assert result == [docs[1], docs[2]]
    post.assert_called_once()
    _, kwargs = post.call_args
    assert kwargs["json"]["documents"] == ["irrelevant", "relevant", "somewhat relevant"]
    assert kwargs["json"]["top_n"] == 2


def test_reranking_retriever_falls_back_on_request_failure():
    docs = _docs("a", "b", "c")
    retriever = _RerankingRetriever(inner=_FakeRetriever(docs=docs), top_k=2)

    with patch("src.retrieval.hybrid._rerank", side_effect=RuntimeError("boom")):
        result = retriever.invoke("query")

    assert result == docs[:2]


def test_reranking_retriever_uses_rerank_result_on_success():
    docs = _docs("a", "b", "c")
    retriever = _RerankingRetriever(inner=_FakeRetriever(docs=docs), top_k=2)

    with patch("src.retrieval.hybrid._rerank", return_value=[docs[2], docs[0]]) as rerank:
        result = retriever.invoke("query")

    assert result == [docs[2], docs[0]]
    rerank.assert_called_once_with("query", docs, 2)


def test_reranking_retriever_returns_empty_without_calling_rerank():
    retriever = _RerankingRetriever(inner=_FakeRetriever(docs=[]), top_k=2)

    with patch("src.retrieval.hybrid._rerank") as rerank:
        result = retriever.invoke("query")

    assert result == []
    rerank.assert_not_called()


def test_parent_expander_dedups_siblings_and_returns_parent_text():
    # Two children share parent p1, one belongs to p2 — distinct parents only, in order.
    children = [
        _child("child a1", "p1"),
        _child("child a2", "p1"),
        _child("child b1", "p2"),
    ]
    retriever = _ParentExpandingRetriever(inner=_FakeRetriever(docs=children), top_k=6)
    parents = {
        "p1": ("PARENT ONE full section", {"court_name": "BGH"}),
        "p2": ("PARENT TWO full section", {"court_name": "LG"}),
    }
    with patch(
        "src.retrieval.hybrid.db.fetch_case_law_parents", return_value=parents
    ) as fetch:
        result = retriever.invoke("query")

    assert [d.page_content for d in result] == [
        "PARENT ONE full section",
        "PARENT TWO full section",
    ]
    # Only distinct parent ids are fetched, in first-seen order.
    fetch.assert_called_once_with(["p1", "p2"])
    # The first child's citation metadata is carried onto the returned parent doc.
    assert result[0].metadata["parent_id"] == "p1"


def test_parent_expander_caps_at_top_k_distinct_parents():
    children = [_child(f"c{i}", f"p{i}") for i in range(10)]
    retriever = _ParentExpandingRetriever(inner=_FakeRetriever(docs=children), top_k=3)
    parents = {f"p{i}": (f"parent {i}", {}) for i in range(10)}
    with patch("src.retrieval.hybrid.db.fetch_case_law_parents", return_value=parents):
        result = retriever.invoke("query")
    assert [d.page_content for d in result] == ["parent 0", "parent 1", "parent 2"]


def test_parent_expander_falls_back_to_child_when_parent_row_missing():
    children = [_child("child text", "p1")]
    retriever = _ParentExpandingRetriever(inner=_FakeRetriever(docs=children), top_k=6)
    with patch("src.retrieval.hybrid.db.fetch_case_law_parents", return_value={}):
        result = retriever.invoke("query")
    # Parent id present but no row stored -> keep the child's own content.
    assert [d.page_content for d in result] == ["child text"]


def test_parent_expander_falls_back_to_children_without_parent_id():
    children = [_child("bare a", None), _child("bare b", None)]
    retriever = _ParentExpandingRetriever(inner=_FakeRetriever(docs=children), top_k=6)
    with patch("src.retrieval.hybrid.db.fetch_case_law_parents", return_value={}) as fetch:
        result = retriever.invoke("query")
    assert [d.page_content for d in result] == ["bare a", "bare b"]
    fetch.assert_called_once_with([])


def _cdoc(text: str, chunk_id: str) -> Document:
    return Document(page_content=text, metadata={"chunk_id": chunk_id})


def test_extract_court_filter_matches_bgh():
    assert _extract_court_filter("Was hat der BGH zur Kaution entschieden?") == {
        "court_name": "Bundesgerichtshof"
    }


def test_extract_court_filter_matches_bverfg_before_generic():
    assert _extract_court_filter("Bundesverfassungsgericht Räumungsschutz") == {
        "court_name": "Bundesverfassungsgericht"
    }


def test_extract_court_filter_matches_hoechstrichterlich():
    assert _extract_court_filter("Gibt es höchstrichterliche Rechtsprechung dazu?") == {
        "level_of_appeal": "Bundesgericht"
    }


def test_extract_court_filter_none_without_court_cue():
    assert _extract_court_filter("Wie hoch darf die Kaution sein?") is None


def test_case_law_ensemble_falls_back_when_court_filter_empty(monkeypatch):
    monkeypatch.setattr("src.retrieval.hybrid.config.CASE_LAW_COURT_FILTER", True)
    narrowed = MagicMock()
    narrowed.invoke.return_value = []
    fallback = MagicMock()
    fallback.invoke.return_value = _docs("fallback")
    with patch(
        "src.retrieval.hybrid._build_ensemble", side_effect=[narrowed, fallback]
    ) as build:
        result = _case_law_ensemble("BGH Kaution", None, 20)
    assert [d.page_content for d in result] == ["fallback"]
    assert build.call_count == 2


def test_case_law_ensemble_no_court_filter_single_ensemble(monkeypatch):
    monkeypatch.setattr("src.retrieval.hybrid.config.CASE_LAW_COURT_FILTER", False)
    ensemble = MagicMock()
    ensemble.invoke.return_value = _docs("plain")
    with patch("src.retrieval.hybrid._build_ensemble", return_value=ensemble) as build:
        result = _case_law_ensemble("BGH Kaution", None, 20)
    assert [d.page_content for d in result] == ["plain"]
    build.assert_called_once_with("case_law", None, 20)


def test_case_law_inner_multi_query_merges_and_dedups(monkeypatch):
    monkeypatch.setattr("src.retrieval.hybrid.config.CASE_LAW_MULTI_QUERY", True)
    retriever = _CaseLawInnerRetriever(metadata_filter=None, candidate_k=20)
    per_query = {
        "orig": [_cdoc("a", "c1"), _cdoc("b", "c2")],
        "v1": [_cdoc("b2", "c2"), _cdoc("c", "c3")],  # c2 duplicates across variants
    }
    with (
        patch("src.retrieval.hybrid._expand_queries", return_value=["v1"]),
        patch(
            "src.retrieval.hybrid._case_law_ensemble",
            side_effect=lambda q, f, k: per_query["orig" if q == "orig" else "v1"],
        ),
    ):
        result = retriever.invoke("orig")
    # First-seen order, deduped by chunk_id: c1, c2, c3 (not the second c2).
    assert [d.metadata["chunk_id"] for d in result] == ["c1", "c2", "c3"]


def test_case_law_inner_single_query_when_multiquery_off(monkeypatch):
    monkeypatch.setattr("src.retrieval.hybrid.config.CASE_LAW_MULTI_QUERY", False)
    retriever = _CaseLawInnerRetriever(metadata_filter=None, candidate_k=20)
    with (
        patch("src.retrieval.hybrid._expand_queries") as expand,
        patch(
            "src.retrieval.hybrid._case_law_ensemble",
            return_value=[_cdoc("a", "c1")],
        ) as ens,
    ):
        result = retriever.invoke("orig")
    assert [d.metadata["chunk_id"] for d in result] == ["c1"]
    expand.assert_not_called()
    ens.assert_called_once()


def test_expand_queries_returns_empty_on_llm_failure():
    with patch("src.retrieval.hybrid.init_chat_model", side_effect=RuntimeError("boom")):
        assert _expand_queries("Kündigungsfrist") == []


def test_expand_queries_parses_lines_and_drops_echo(monkeypatch):
    monkeypatch.setattr("src.retrieval.hybrid.config.MULTI_QUERY_N", 3)
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = MagicMock(content="Kündigungsfrist\n- Frist Kündigung\n2. Mietende")
    with patch("src.retrieval.hybrid.init_chat_model", return_value=fake_llm):
        variants = _expand_queries("Kündigungsfrist")
    # The echo of the original ("Kündigungsfrist") is dropped; list markers stripped.
    assert "Kündigungsfrist" not in variants
    assert "Frist Kündigung" in variants
    assert "2. Mietende" in variants or "Mietende" in variants


def test_statutes_retriever_falls_back_when_section_filter_yields_nothing():
    retriever = _StatutesRetriever(metadata_filter=None, candidate_k=20)
    narrowed_ensemble = MagicMock()
    narrowed_ensemble.invoke.return_value = []
    fallback_docs = _docs("fallback result")
    fallback_ensemble = MagicMock()
    fallback_ensemble.invoke.return_value = fallback_docs

    with patch(
        "src.retrieval.hybrid._build_ensemble",
        side_effect=[narrowed_ensemble, fallback_ensemble],
    ) as build:
        result = retriever.invoke("§ 999 gibt es nicht")

    assert result == fallback_docs
    assert build.call_count == 2


def test_statutes_retriever_uses_section_filter_when_it_finds_results():
    retriever = _StatutesRetriever(metadata_filter=None, candidate_k=20)
    narrowed_docs = _docs("the right section")
    narrowed_ensemble = MagicMock()
    narrowed_ensemble.invoke.return_value = narrowed_docs

    with patch(
        "src.retrieval.hybrid._build_ensemble", return_value=narrowed_ensemble
    ) as build:
        result = retriever.invoke("§ 535 Pflichten des Vermieters")

    assert result == narrowed_docs
    build.assert_called_once_with("statutes", {"section": "§ 535"}, 20)


def test_statutes_retriever_skips_filter_without_citation():
    retriever = _StatutesRetriever(metadata_filter=None, candidate_k=20)
    docs = _docs("unfiltered result")
    ensemble = MagicMock()
    ensemble.invoke.return_value = docs

    with patch("src.retrieval.hybrid._build_ensemble", return_value=ensemble) as build:
        result = retriever.invoke("Wann darf der Vermieter kündigen?")

    assert result == docs
    build.assert_called_once_with("statutes", None, 20)
