"""LLM price table. Kept central so cost math is auditable in one place.

Prices as of model launch. Update here when providers change pricing.
All prices in USD per 1M tokens.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    prompt_per_mtok: float
    completion_per_mtok: float


# Keep conservative. Vision input tokens are priced the same as text for 4o.
_PRICE_TABLE: dict[str, ModelPrice] = {
    # --- OpenAI / Azure OpenAI ---
    "gpt-4o": ModelPrice(prompt_per_mtok=2.50, completion_per_mtok=10.00),
    "gpt-4o-2024-08-06": ModelPrice(prompt_per_mtok=2.50, completion_per_mtok=10.00),
    "gpt-4o-mini": ModelPrice(prompt_per_mtok=0.15, completion_per_mtok=0.60),
    "gpt-4o-mini-2024-07-18": ModelPrice(prompt_per_mtok=0.15, completion_per_mtok=0.60),
    # --- Google Gemini ---
    "gemini-2.5-flash": ModelPrice(prompt_per_mtok=0.15, completion_per_mtok=0.60),
    "gemini-2.5-pro": ModelPrice(prompt_per_mtok=1.25, completion_per_mtok=10.00),
    "gemini-2.0-flash": ModelPrice(prompt_per_mtok=0.10, completion_per_mtok=0.40),
    "gemini-1.5-pro": ModelPrice(prompt_per_mtok=1.25, completion_per_mtok=5.00),
    "gemini-1.5-flash": ModelPrice(prompt_per_mtok=0.075, completion_per_mtok=0.30),
}

_FALLBACK = ModelPrice(prompt_per_mtok=2.50, completion_per_mtok=10.00)


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return USD cost for a single LLM call. Unknown models use the 4o price."""
    price = _PRICE_TABLE.get(model, _FALLBACK)
    return round(
        (tokens_in / 1_000_000) * price.prompt_per_mtok
        + (tokens_out / 1_000_000) * price.completion_per_mtok,
        6,
    )
