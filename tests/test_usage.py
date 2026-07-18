from src import config
from src.usage import cost_usd, summarize


class _StubCallback:
    def __init__(self, usage_metadata: dict) -> None:
        self.usage_metadata = usage_metadata


def test_cost_usd_prices_known_model():
    haiku = "anthropic/claude-haiku-4.5"
    price_in, price_out = config.MODEL_PRICING[haiku]
    by_model = {haiku: {"input_tokens": 1_000_000, "output_tokens": 1_000_000}}
    assert cost_usd(by_model) == price_in + price_out


def test_cost_usd_ignores_unpriced_model():
    # The embedding model (and any model absent from MODEL_PRICING) is priced at 0.
    by_model = {"text-embedding-3-large": {"input_tokens": 5_000_000, "output_tokens": 0}}
    assert cost_usd(by_model) == 0.0


def test_cost_usd_sums_multiple_models():
    by_model = {
        "anthropic/claude-haiku-4.5": {"input_tokens": 1_000_000, "output_tokens": 0},  # $1.00
        "google/gemini-2.5-flash": {"input_tokens": 0, "output_tokens": 1_000_000},  # $0.60
    }
    assert round(cost_usd(by_model), 6) == 1.60


def test_summarize_shape_and_totals():
    by_model = {
        "anthropic/claude-haiku-4.5": {"input_tokens": 100, "output_tokens": 20},
        "google/gemini-2.5-flash": {"input_tokens": 300, "output_tokens": 50},
    }
    out = summarize(_StubCallback(by_model))
    assert out["input_tokens"] == 400
    assert out["output_tokens"] == 70
    assert out["by_model"] == by_model
    assert out["cost_usd"] >= 0


def test_summarize_empty():
    out = summarize(_StubCallback({}))
    assert out == {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "by_model": {}}
