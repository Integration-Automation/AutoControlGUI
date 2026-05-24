"""Per-call LLM cost telemetry — token counts + estimated USD.

Public surface::

    from je_auto_control import (
        CostEvent, CostSummary, default_cost_store, estimate_llm_usd,
        record_llm_call, summarise_llm_costs,
    )

    record_llm_call(
        provider="anthropic", model="claude-opus-4-7",
        input_tokens=512, output_tokens=128, label="vlm_locate",
    )
    summary = summarise_llm_costs()
    print(summary.total_usd, summary.by_model)
"""
from je_auto_control.utils.cost_telemetry.pricing import (
    Pricing, estimate_usd as estimate_llm_usd, known_models, pricing_for,
)
from je_auto_control.utils.cost_telemetry.store import (
    CostEvent, CostStore, CostSummary, default_cost_store,
    summarise_events as summarise_llm_costs,
)


def record_llm_call(*, provider: str, model: str,
                    input_tokens: int, output_tokens: int,
                    label=None, run_id=None, user=None) -> CostEvent:
    """Convenience wrapper around ``default_cost_store.record``."""
    return default_cost_store.record(
        provider=provider, model=model,
        input_tokens=input_tokens, output_tokens=output_tokens,
        label=label, run_id=run_id, user=user,
    )


__all__ = [
    "CostEvent", "CostStore", "CostSummary", "Pricing",
    "default_cost_store", "estimate_llm_usd", "known_models",
    "pricing_for", "record_llm_call", "summarise_llm_costs",
]
