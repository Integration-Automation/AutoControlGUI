"""Tests for the LLM cost telemetry layer."""
from pathlib import Path

import pytest

from je_auto_control.utils.cost_telemetry import (
    CostEvent, CostStore, estimate_llm_usd, record_llm_call,
)
from je_auto_control.utils.cost_telemetry.pricing import (
    Pricing, known_models, pricing_for,
)


@pytest.fixture
def temp_store(tmp_path: Path) -> CostStore:
    return CostStore(path=tmp_path / "events.jsonl")


# === Pricing ==============================================================

def test_pricing_for_known_model_returns_pricing():
    pricing = pricing_for("claude-opus-4-7")
    assert isinstance(pricing, Pricing)
    assert pricing.input_per_million > 0
    assert pricing.output_per_million > pricing.input_per_million


def test_pricing_for_unknown_model_returns_none():
    assert pricing_for("not-a-real-model") is None


def test_estimate_usd_uses_known_pricing():
    cost = estimate_llm_usd(
        "claude-haiku-4-5-20251001", 1_000_000, 1_000_000,
    )
    # 1M in + 1M out at $1/$5 per million = $6
    assert cost == pytest.approx(6.0, rel=0.01)


def test_estimate_usd_returns_zero_for_unknown_model():
    assert estimate_llm_usd("not-real", 1000, 1000) == 0.0


def test_estimate_usd_respects_override():
    cost = estimate_llm_usd(
        "claude-haiku-4-5-20251001", 1_000_000, 0,
        override={"claude-haiku-4-5-20251001": Pricing(2.0, 10.0)},
    )
    assert cost == pytest.approx(2.0, rel=0.01)


def test_known_models_returns_sorted_list():
    models = known_models()
    assert models == sorted(models)
    assert "claude-opus-4-7" in models


# === Store ================================================================

def test_record_appends_event_with_auto_estimate(temp_store):
    event = temp_store.record(
        provider="anthropic", model="claude-opus-4-7",
        input_tokens=100, output_tokens=50,
    )
    assert isinstance(event, CostEvent)
    assert event.estimated_usd > 0
    assert temp_store.list_events() == [event]


def test_record_honours_explicit_cost(temp_store):
    event = temp_store.record(
        provider="custom", model="unknown",
        input_tokens=100, output_tokens=50,
        estimated_usd=2.5,
    )
    assert event.estimated_usd == 2.5


def test_record_stamps_provider_model_and_label(temp_store):
    event = temp_store.record(
        provider="anthropic", model="claude-opus-4-7",
        input_tokens=10, output_tokens=20, label="vlm_locate",
        run_id="run-123", user="alice",
    )
    assert event.provider == "anthropic"
    assert event.label == "vlm_locate"
    assert event.run_id == "run-123"
    assert event.user == "alice"


def test_clear_removes_file(temp_store):
    temp_store.record(provider="x", model="y",
                       input_tokens=1, output_tokens=1)
    assert temp_store.path.exists()
    temp_store.clear()
    assert temp_store.list_events() == []
    assert not temp_store.path.exists()


def test_list_events_respects_limit(temp_store):
    for index in range(5):
        temp_store.record(provider="anthropic", model="claude-opus-4-7",
                           input_tokens=index, output_tokens=index)
    assert len(temp_store.list_events(limit=3)) == 3


def test_list_events_skips_malformed_lines(temp_store):
    temp_store.path.parent.mkdir(parents=True, exist_ok=True)
    with temp_store.path.open("w", encoding="utf-8") as fp:
        fp.write("not-json\n")
        fp.write('{"timestamp": "t", "provider": "p", "model": "m", '
                 '"input_tokens": 1, "output_tokens": 1, '
                 '"estimated_usd": 0.1}\n')
    events = temp_store.list_events()
    assert len(events) == 1
    assert events[0].provider == "p"


# === Summarise ============================================================

def test_summarise_aggregates_by_model_provider_day(temp_store):
    temp_store.record(provider="anthropic", model="claude-opus-4-7",
                       input_tokens=1000, output_tokens=500)
    temp_store.record(provider="anthropic", model="claude-opus-4-7",
                       input_tokens=2000, output_tokens=500)
    temp_store.record(provider="openai", model="gpt-4o-mini",
                       input_tokens=10000, output_tokens=5000)
    summary = temp_store.summarise()
    assert summary.total_calls == 3
    assert "claude-opus-4-7" in summary.by_model
    assert "openai" in summary.by_provider
    assert summary.total_input_tokens == 13000


def test_summarise_handles_empty_log():
    empty_store = CostStore(path=Path("/tmp/never_exists.jsonl"))
    assert empty_store.summarise().total_calls == 0


def test_record_llm_call_uses_default_store(monkeypatch, tmp_path):
    from je_auto_control.utils.cost_telemetry import store as store_mod
    monkeypatch.setattr(store_mod.default_cost_store, "_path",
                         tmp_path / "evt.jsonl")
    event = record_llm_call(
        provider="anthropic", model="claude-opus-4-7",
        input_tokens=1, output_tokens=1,
    )
    assert isinstance(event, CostEvent)


# === Serialisation ========================================================

def test_event_to_dict_round_trips(temp_store):
    event = temp_store.record(
        provider="x", model="y",
        input_tokens=1, output_tokens=2,
    )
    assert CostEvent(**event.to_dict()) == event


def test_summary_to_dict_includes_breakdowns(temp_store):
    temp_store.record(provider="anthropic", model="claude-opus-4-7",
                       input_tokens=1, output_tokens=1)
    data = temp_store.summarise().to_dict()
    assert "by_model" in data
    assert "by_provider" in data
    assert "by_day" in data


# === Executor / MCP / facade =============================================

def test_executor_registers_cost_commands():
    from je_auto_control.utils.executor.action_executor import executor
    assert {
        "AC_costs_record", "AC_costs_summary",
        "AC_costs_list", "AC_costs_clear",
    } <= executor.known_commands()


def test_mcp_factory_registers_cost_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_costs_record", "ac_costs_summary",
             "ac_costs_list"} <= names


def test_facade_exports_cost_api():
    import je_auto_control as ac
    for name in ("CostEvent", "CostSummary", "default_cost_store",
                  "estimate_llm_usd", "record_llm_call",
                  "summarise_llm_costs"):
        assert hasattr(ac, name)
