from unittest.mock import MagicMock, patch

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.retrieval.hybrid import (
    _RerankingRetriever,
    _StatutesRetriever,
    _extract_section_filter,
    _rerank,
)


def _docs(*texts: str) -> list[Document]:
    return [Document(page_content=t) for t in texts]


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
