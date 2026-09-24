"""Per-model token pricing table (USD per 1M tokens).

Numbers are list prices for the public API tier (Claude: the Anthropic
pricing page as of September 2026); treat them as an estimate, not an
invoice. A dated or provider-prefixed Claude id (``claude-haiku-4-5-20251001``,
``anthropic.claude-opus-5``, ``claude-opus-4-5@20251101``) is looked up by its
base id. ``estimate_usd`` returns 0.0 for any unknown model rather than
raising — the goal is best-effort visibility, not strict accounting.

Override per call by passing an explicit ``Pricing`` dict to
:func:`estimate_usd`, e.g. when reading negotiated rates from a config
bundle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Pricing:
    """USD per 1M tokens for one model."""

    input_per_million: float
    output_per_million: float


_DEFAULT_PRICING: Dict[str, Pricing] = {
    # Anthropic Claude, current list prices (Opus 4.7 was listed at the
    # Opus 4.1 price, three times too high).
    "claude-fable-5-1": Pricing(10.0, 50.0),
    "claude-fable-5": Pricing(10.0, 50.0),
    "claude-opus-5-5": Pricing(4.0, 20.0),
    "claude-opus-5": Pricing(5.0, 25.0),
    "claude-opus-4-8": Pricing(5.0, 25.0),
    "claude-opus-4-7": Pricing(5.0, 25.0),
    "claude-opus-4-6": Pricing(5.0, 25.0),
    "claude-opus-4-5": Pricing(5.0, 25.0),
    "claude-opus-4-1": Pricing(15.0, 75.0),
    "claude-opus-4": Pricing(15.0, 75.0),
    "claude-sonnet-5": Pricing(2.0, 10.0),
    "claude-sonnet-4-6": Pricing(3.0, 15.0),
    "claude-sonnet-4-5": Pricing(3.0, 15.0),
    "claude-sonnet-4": Pricing(3.0, 15.0),
    "claude-haiku-4-5": Pricing(1.0, 5.0),
    # Earlier Claude lines, kept so old scripts still report something.
    "claude-3-7-sonnet": Pricing(3.0, 15.0),
    "claude-3-5-sonnet": Pricing(3.0, 15.0),
    "claude-3-5-haiku": Pricing(0.8, 4.0),
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
    return _DEFAULT_PRICING.get(model) or _DEFAULT_PRICING.get(_base_model_id(model))


#: A provider prefix ("anthropic.", "us.anthropic."), a date or version
#: suffix ("-20251001", "@20251101", "-v1:0") around a Claude id.
_PROVIDER_PREFIX = re.compile(r"^(?:[a-z]{2,4}\.)?anthropic\.")
_ID_SUFFIX = re.compile(r"(?:[-@]\d{8})?(?:-v\d+(?::\d+)?)?$")


def _base_model_id(model: str) -> str:
    """``model`` without a provider prefix or a date / version suffix."""
    return _ID_SUFFIX.sub("", _PROVIDER_PREFIX.sub("", str(model)), count=1)


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
