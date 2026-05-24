"""Per-model token pricing table (USD per 1M tokens).

Numbers are list prices for the public API tier as of mid-2025; treat
them as an estimate, not an invoice. ``estimate_usd`` returns 0.0 for
any unknown model rather than raising — the goal is best-effort
visibility, not strict accounting.

Override per call by passing an explicit ``Pricing`` dict to
:func:`estimate_usd`, e.g. when reading negotiated rates from a config
bundle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens for one model."""

    input_per_million: float
    output_per_million: float


_DEFAULT_PRICING: Dict[str, Pricing] = {
    # Anthropic Claude 4 family
    "claude-opus-4-7": Pricing(15.0, 75.0),
    "claude-sonnet-4-6": Pricing(3.0, 15.0),
    "claude-haiku-4-5-20251001": Pricing(1.0, 5.0),
    # Earlier Claude lines, kept so old scripts still report something.
    "claude-3-5-sonnet": Pricing(3.0, 15.0),
    "claude-3-5-haiku": Pricing(1.0, 5.0),
    "claude-3-opus": Pricing(15.0, 75.0),
    # OpenAI
    "gpt-4o": Pricing(2.5, 10.0),
    "gpt-4o-mini": Pricing(0.15, 0.60),
    "gpt-4-turbo": Pricing(10.0, 30.0),
    "o1": Pricing(15.0, 60.0),
    "o1-mini": Pricing(3.0, 12.0),
}


def pricing_for(model: str,
                override: Optional[Dict[str, Pricing]] = None,
                ) -> Optional[Pricing]:
    """Return ``Pricing`` for ``model`` or ``None`` when unknown."""
    if override and model in override:
        return override[model]
    return _DEFAULT_PRICING.get(model)


def estimate_usd(model: str, input_tokens: int, output_tokens: int,
                  override: Optional[Dict[str, Pricing]] = None,
                  ) -> float:
    """Return the rounded USD estimate for one LLM call."""
    pricing = pricing_for(model, override)
    if pricing is None:
        return 0.0
    cost = (
        (max(0, int(input_tokens)) * pricing.input_per_million / 1_000_000.0)
        + (max(0, int(output_tokens)) * pricing.output_per_million / 1_000_000.0)
    )
    return round(cost, 6)


def known_models() -> list:
    """Sorted list of every model the default pricing table covers."""
    return sorted(_DEFAULT_PRICING)


__all__ = ["Pricing", "estimate_usd", "known_models", "pricing_for"]
