"""The single consolidated RAGAs evaluation runner.

Two passes over `src.eval.dataset.EVAL_DATASET`, scored against the single
`config.THRESHOLDS`:

1. Agent (end-to-end): runs each question through the compiled graph
   (`src.agent.graph.build_graph`) on an ephemeral thread, collects the tool
   results from the run as `contexts`, and scores faithfulness,
   answer_relevancy, context_precision and context_recall.
2. Retrieval (per collection): runs each question's hybrid retriever
   (`src.retrieval.hybrid.get_hybrid_retriever`) directly and scores
   context_precision/context_recall, isolating retrieval quality from the
   agent's tool-calling behaviour.

Run with:
    uv run python main.py eval
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import SecretStr

from src import config
from src.agent.graph import RECURSION_LIMIT, build_graph
from src.agent.state import Context
from src.eval.dataset import EVAL_DATASET
from src.usage import make_usage_callback, summarize

logger = logging.getLogger(__name__)

_AGENT_METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
_RETRIEVAL_METRICS = ["context_precision", "context_recall"]


def _hit_metrics(retrieved: list[tuple[dict[str, Any], list[Any]]]) -> dict[str, float]:
    """Deterministic, judge-free retrieval metrics over already-retrieved docs.

    For each item annotated with a gold `reference_file_number`, checks whether a
    retrieved doc's `file_number` metadata matches it and at what rank, yielding
    `hit_rate` (fraction whose gold decision was retrieved) and `mrr` (mean reciprocal
    rank). Returns `{}` when no item carries a reference (e.g. the statutes collection),
    so it contributes nothing there.
    """
    scored = [(item, docs) for item, docs in retrieved if item.get("reference_file_number")]
    if not scored:
        return {}
    hits = 0
    rr_sum = 0.0
    for item, docs in scored:
        gold = str(item["reference_file_number"])
        rank = next(
            (
                i
                for i, d in enumerate(docs, start=1)
                if (fn := str(getattr(d, "metadata", {}).get("file_number") or ""))
                and (gold in fn or fn in gold)
            ),
            None,
        )
        if rank is not None:
            hits += 1
            rr_sum += 1.0 / rank
    n = len(scored)
    return {"hit_rate": round(hits / n, 3), "mrr": round(rr_sum / n, 3)}


def _make_judge_llm() -> Any:
    from langchain.chat_models import init_chat_model

    # max_retries: the OpenAI SDK's own default (2) is too thin for the
    # occasional transient APIConnectionError seen against OpenRouter — this is
    # the layer that actually retries a single failed HTTP call (cheap), versus
    # RunConfig's retries below which re-run a whole ragas job (costlier).
    return init_chat_model(
        config.LLM_JUDGE,
        model_provider="openai",
        base_url=config.LLM_BASE_URL,
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        temperature=0,
        max_tokens=8192,
        max_retries=5,
    )


def _make_judge_embeddings() -> Any:
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=config.RAGAS_EMBEDDING_MODEL,
        base_url=config.LLM_BASE_URL,
        api_key=SecretStr(os.environ.get("OPENAI_API_KEY", "")),
    )


def _ragas_score(
    rows: list[dict[str, Any]], metric_names: list[str], usage_cb: Any = None
) -> dict[str, float]:
    """Score `rows` (question/answer/contexts/ground_truth) on `metric_names`.

    `usage_cb`, when given, is passed to RAGAs so the judge LLM's token usage is
    aggregated into the shared handler.
    """
    from datasets import Dataset  # type: ignore[import-untyped]
    from ragas import evaluate as ragas_evaluate  # type: ignore[import-not-found]
    from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore[import-not-found]
    from ragas.llms import LangchainLLMWrapper  # type: ignore[import-not-found]
    from ragas.metrics import (  # type: ignore[import-not-found]
        AnswerRelevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from ragas.run_config import RunConfig  # type: ignore[import-not-found]

    # strictness=1: the judge model (config.LLM_JUDGE, via OpenRouter) only ever
    # returns 1 generation regardless of how many are requested, so the default
    # strictness=3 just wastes a request and logs a spurious "returned 1
    # generations instead of requested 3" warning on every call.
    metric_map = {
        "faithfulness": faithfulness,
        "answer_relevancy": AnswerRelevancy(strictness=1),
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    metrics = [metric_map[name] for name in metric_names]

    dataset = Dataset.from_list(rows)
    # max_retries at RAGAs' own default (10): the per-collection eval sets are small,
    # so a single transient APIConnectionError is highly visible — one failed row can
    # noticeably skew the available data for that metric.
    run_config = RunConfig(timeout=180, max_retries=10, max_wait=60)
    raw_result: Any = ragas_evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=LangchainLLMWrapper(_make_judge_llm()),
        embeddings=LangchainEmbeddingsWrapper(_make_judge_embeddings()),
        run_config=run_config,
        raise_exceptions=False,
        callbacks=[usage_cb] if usage_cb is not None else None,
    )
    scores_df = raw_result.to_pandas()

    result: dict[str, float] = {}
    for name in metric_names:
        col = scores_df[name]
        nan_mask = col.isna()
        if nan_mask.any():
            offending = scores_df.loc[nan_mask, "user_input"] if "user_input" in scores_df.columns else None
            if offending is None and "question" in scores_df.columns:
                offending = scores_df.loc[nan_mask, "question"]
            logger.warning(
                "RAGAs metric %r returned NaN for %d/%d rows%s",
                name,
                int(nan_mask.sum()),
                len(col),
                f"; questions: {list(offending)}" if offending is not None else "",
            )
        vals = [v for v in col.tolist() if v == v]  # drop NaN
        result[name] = round(sum(vals) / len(vals), 3) if vals else float("nan")
    return result


def _all_nan(scores: dict[str, float]) -> bool:
    """True if every metric in `scores` is NaN (a transient judge failure, not a real 0)."""
    return bool(scores) and all(v != v for v in scores.values())


def _load_previous_retrieval(output_path: Path) -> dict[str, dict[str, float]]:
    """Best-effort read of the last run's per-collection retrieval block, for NaN fallback."""
    try:
        prev = json.loads(output_path.read_text(encoding="utf-8"))
        return dict(prev.get("retrieval", {}))
    except (OSError, ValueError):
        return {}


def _run_agent_turn(question: str, usage_cb: Any = None) -> tuple[str, list[str]]:
    """Run one ephemeral-thread agent turn; return (answer, tool-result contexts).

    `usage_cb`, when given, is attached so this turn's LLM usage (agent + any
    tool-internal LLM calls) is aggregated into the shared handler.

    Each turn uses a throwaway `eval-<uuid>` thread. Its checkpoint rows are left in
    the checkpointer (harmless, orphaned) — acceptable for an occasional eval run; a
    periodic sweep of `eval-*` threads would reclaim the space if it ever mattered."""
    graph = build_graph()
    thread_id = f"eval-{uuid.uuid4()}"
    run_config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
        "callbacks": [usage_cb] if usage_cb is not None else [],
    }
    result = graph.invoke(
        {"messages": [HumanMessage(content=question)]},
        config=run_config,
        context=Context(user_name="eval", role="mieter"),
    )
    messages = result["messages"]
    answer = str(messages[-1].content)
    contexts = [str(m.content) for m in messages if isinstance(m, ToolMessage)]
    return answer, contexts or [""]


def _print_table(title: str, scores: dict[str, float]) -> None:
    separator = "+" + "-" * 23 + "+" + "-" * 9 + "+" + "-" * 10 + "+"
    print(f"\n{title}")
    print(separator)
    print(f"| {'Metric':<21} | {'Score':>7} | {'Status':<8} |")
    print(separator)
    for metric, threshold in config.THRESHOLDS.items():
        if metric not in scores:
            continue
        score = scores[metric]
        if score != score:  # NaN
            status = "N/A"
        elif score < threshold:
            status = "WARN"
        else:
            status = "OK"
        print(f"| {metric:<21} | {score:>7.2f} | {status:<8} |")
    print(separator)


def run_eval(
    dataset: list[dict[str, Any]] | None = None,
    output_path: Path = Path("data/eval_results.json"),
) -> dict[str, Any]:
    """Run the consolidated RAGAs evaluation and save/return the results."""
    if dataset is None:
        dataset = EVAL_DATASET

    # One handler aggregates token usage across every LLM call in this run — the agent
    # turns and their tools, plus the RAGAs judge — so the eval reports its own cost.
    usage_cb = make_usage_callback()

    logger.info("Running agent end-to-end for %d questions...", len(dataset))
    agent_rows = []
    for item in dataset:
        answer, contexts = _run_agent_turn(item["question"], usage_cb=usage_cb)
        agent_rows.append(
            {
                "question": item["question"],
                "answer": answer,
                "contexts": contexts,
                "ground_truth": item["ground_truth"],
            }
        )
    agent_scores = _ragas_score(agent_rows, _AGENT_METRICS, usage_cb=usage_cb)

    logger.info("Running retrieval-only evaluation per collection...")
    previous_retrieval = _load_previous_retrieval(output_path)
    retrieval_scores: dict[str, dict[str, float]] = {}
    for collection in (config.STATUTES_COLLECTION, config.CASE_LAW_COLLECTION):
        items = [item for item in dataset if item["collection"] == collection]
        if not items:
            continue
        from src.retrieval.hybrid import get_hybrid_retriever

        retriever = get_hybrid_retriever(collection)
        rows = []
        retrieved: list[tuple[dict[str, Any], list[Any]]] = []
        for item in items:
            docs = retriever.invoke(item["question"])
            retrieved.append((item, docs))
            rows.append(
                {
                    "question": item["question"],
                    "answer": item["answer"],
                    "contexts": [d.page_content for d in docs] or [""],
                    "ground_truth": item["ground_truth"],
                }
            )
        scores = _ragas_score(rows, _RETRIEVAL_METRICS, usage_cb=usage_cb)
        # A collection whose every metric is NaN means the judge failed on every row
        # (transient OpenRouter/judge outage), not that the collection has no data — with
        # few rows per collection this is easy to hit. Don't silently overwrite the last
        # good scores with an empty-looking block: warn loudly and keep the previous run's
        # numbers if we have them, so a flaky run can't read as "no data for {collection}".
        if _all_nan(scores):
            prev = previous_retrieval.get(collection)
            logger.warning(
                "Retrieval eval for %r scored NaN on all %d row(s) — likely a transient "
                "judge failure, re-run `main.py eval`.%s",
                collection,
                len(rows),
                " Keeping previous run's scores." if prev and not _all_nan(prev) else "",
            )
            scores = prev if prev and not _all_nan(prev) else scores
        # Deterministic, judge-free retrieval metrics reuse the docs just retrieved (no
        # extra retrieval, no judge): where a gold decision is annotated
        # (`reference_file_number`, case-law only), does it appear in the results
        # (hit_rate@k) and how highly is it ranked (MRR)?
        scores.update(_hit_metrics(retrieved))
        retrieval_scores[collection] = scores

    results: dict[str, Any] = {
        "agent": agent_scores,
        "retrieval": retrieval_scores,
        "usage": summarize(usage_cb),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Results saved to %s", output_path)

    _print_table("Agent (end-to-end)", agent_scores)
    for collection, scores in retrieval_scores.items():
        _print_table(f"Retrieval — {collection}", scores)

    plant = next((item for item in dataset if item.get("is_hallucination_plant")), None)
    faith = agent_scores.get("faithfulness", 1.0)
    if plant and faith == faith and faith < config.THRESHOLDS["faithfulness"]:
        print(
            "\nLow faithfulness: hallucination planted in eval dataset detected "
            f"({plant['notes']})"
        )

    return results
