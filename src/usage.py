"""LLM token-usage capture and cost accounting.

One `UsageMetadataCallbackHandler` (langchain-core) is attached explicitly to every LLM
entry point — the agent graph runs, the tools they call, and the RAGAs judge — so usage
is aggregated per model regardless of threads/async (unlike the contextvar variant, which
would not propagate across RAGAs' worker pool). Cost is derived from
`config.MODEL_PRICING`. Embeddings do not report `usage_metadata`, so this covers chat/
completion LLM calls only.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler

from src import config


def make_usage_callback() -> UsageMetadataCallbackHandler:
    """Return a fresh per-run usage handler to pass in a run's `callbacks`."""
    return UsageMetadataCallbackHandler()


def cost_usd(by_model: dict[str, Any]) -> float:
    """Total USD cost for a per-model usage map, priced via `config.MODEL_PRICING`.

    `by_model` is `UsageMetadataCallbackHandler.usage_metadata`:
    `{model: {"input_tokens": int, "output_tokens": int, ...}}`. Models absent from
    `MODEL_PRICING` (e.g. the embedding model) are priced at 0.
    """
    total = 0.0
    for model, usage in by_model.items():
        price = config.MODEL_PRICING.get(model)
        if not price:
            continue
        input_price, output_price = price
        total += usage.get("input_tokens", 0) / 1_000_000 * input_price
        total += usage.get("output_tokens", 0) / 1_000_000 * output_price
    return total


def summarize(cb: UsageMetadataCallbackHandler) -> dict[str, Any]:
    """Roll a usage handler up into `{input_tokens, output_tokens, cost_usd, by_model}`."""
    by_model = dict(cb.usage_metadata)
    input_tokens = sum(u.get("input_tokens", 0) for u in by_model.values())
    output_tokens = sum(u.get("output_tokens", 0) for u in by_model.values())
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd(by_model), 6),
        "by_model": by_model,
    }
