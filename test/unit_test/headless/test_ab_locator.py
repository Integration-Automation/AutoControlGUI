"""Tests for the A/B locator framework."""
from pathlib import Path

import pytest

from je_auto_control.utils.ab_locator import (
    ABRunOutcome, ABStore, ab_locate,
)
from je_auto_control.utils.ab_locator import runner as runner_mod
from je_auto_control.utils.anchor_locator import image_locator


@pytest.fixture
def temp_store(tmp_path: Path) -> ABStore:
    return ABStore(path=tmp_path / "ab.json")


def _patch_locator_resolutions(monkeypatch, mapping):
    """``mapping`` maps Locator.template_path → coords-or-None."""
    def fake_resolve(locator):
        return mapping.get(getattr(locator, "template_path", None))
    monkeypatch.setattr(runner_mod, "_resolve_single", fake_resolve)


# === ab_locate ============================================================

def test_ab_locate_records_winner_and_results(monkeypatch, temp_store):
    _patch_locator_resolutions(monkeypatch, {
        "fast.png": (10, 20),
        "slow.png": (30, 40),
        "miss.png": None,
    })
    outcome = ab_locate(
        target_id="submit",
        strategies={
            "fast": image_locator("fast.png"),
            "slow": image_locator("slow.png"),
            "miss": image_locator("miss.png"),
        },
        store=temp_store,
    )
    assert isinstance(outcome, ABRunOutcome)
    assert outcome.winner in {"fast", "slow"}
    assert outcome.results["miss"].succeeded is False
    assert outcome.results["fast"].coordinates == (10, 20)


def test_ab_locate_returns_none_winner_when_all_miss(monkeypatch, temp_store):
    _patch_locator_resolutions(monkeypatch, {
        "a.png": None, "b.png": None,
    })
    outcome = ab_locate(
        target_id="nope",
        strategies={
            "a": image_locator("a.png"),
            "b": image_locator("b.png"),
        },
        store=temp_store, record=False,
    )
    assert outcome.winner is None


def test_ab_locate_rejects_empty_strategies():
    with pytest.raises(ValueError):
        ab_locate(target_id="x", strategies={})


def test_ab_locate_rejects_blank_target_id():
    with pytest.raises(ValueError):
        ab_locate(target_id="   ",
                   strategies={"a": image_locator("a.png")})


def test_ab_locate_skips_recording_when_disabled(monkeypatch, temp_store):
    _patch_locator_resolutions(monkeypatch, {"a.png": (0, 0)})
    ab_locate(
        target_id="t", strategies={"a": image_locator("a.png")},
        record=False, store=temp_store,
    )
    assert temp_store.report("t").strategies == []


# === ABStore ==============================================================

def test_store_records_success_and_failure(temp_store):
    temp_store.record(target_id="t", strategy="image",
                       succeeded=True, elapsed_ms=12.0)
    temp_store.record(target_id="t", strategy="image",
                       succeeded=False, elapsed_ms=8.0)
    report = temp_store.report("t")
    assert len(report.strategies) == 1
    stats = report.strategies[0]
    assert stats.successes == 1
    assert stats.failures == 1
    assert stats.success_rate == pytest.approx(0.5)
    assert stats.average_ms == pytest.approx(10.0)


def test_best_strategy_returns_higher_success_rate(temp_store):
    for _ in range(8):
        temp_store.record(target_id="t", strategy="image",
                           succeeded=True, elapsed_ms=5.0)
    for _ in range(2):
        temp_store.record(target_id="t", strategy="image",
                           succeeded=False, elapsed_ms=5.0)
    for _ in range(3):
        temp_store.record(target_id="t", strategy="ocr",
                           succeeded=True, elapsed_ms=2.0)
    for _ in range(7):
        temp_store.record(target_id="t", strategy="ocr",
                           succeeded=False, elapsed_ms=2.0)
    winner = temp_store.report("t").best_strategy()
    assert winner.strategy == "image"


def test_best_strategy_breaks_tie_by_speed(temp_store):
    for _ in range(5):
        temp_store.record(target_id="t", strategy="slow",
                           succeeded=True, elapsed_ms=20.0)
    for _ in range(5):
        temp_store.record(target_id="t", strategy="fast",
                           succeeded=True, elapsed_ms=5.0)
    winner = temp_store.report("t").best_strategy()
    assert winner.strategy == "fast"


def test_store_persists_to_disk_and_reloads(tmp_path):
    path = tmp_path / "ab.json"
    first = ABStore(path=path)
    first.record(target_id="t", strategy="image",
                  succeeded=True, elapsed_ms=1.0)
    assert path.exists()
    second = ABStore(path=path)
    stats = second.report("t").strategies[0]
    assert stats.successes == 1


def test_clear_removes_file(temp_store):
    temp_store.record(target_id="t", strategy="image",
                       succeeded=True, elapsed_ms=1.0)
    temp_store.clear()
    assert temp_store.report("t").strategies == []
    assert not temp_store.path.exists()


def test_report_to_dict_includes_winner(temp_store):
    temp_store.record(target_id="t", strategy="image",
                       succeeded=True, elapsed_ms=1.0)
    data = temp_store.report("t").to_dict()
    assert data["best_strategy"] == "image"
    assert data["best_success_rate"] == 1.0


def test_all_reports_lists_every_target(temp_store):
    temp_store.record(target_id="a", strategy="x",
                       succeeded=True, elapsed_ms=1.0)
    temp_store.record(target_id="b", strategy="x",
                       succeeded=False, elapsed_ms=1.0)
    targets = {r.target_id for r in temp_store.all_reports()}
    assert targets == {"a", "b"}


# === Executor / MCP / facade =============================================

def test_executor_registers_ab_commands():
    from je_auto_control.utils.executor.action_executor import executor
    assert {
        "AC_ab_locate", "AC_ab_report", "AC_ab_best_strategy",
        "AC_ab_clear",
    } <= executor.known_commands()


def test_mcp_factory_registers_ab_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_ab_locate", "ac_ab_report",
             "ac_ab_best_strategy"} <= names


def test_facade_exports_ab_api():
    import je_auto_control as ac
    for name in ("ABRunOutcome", "ab_best_strategy", "ab_locate",
                  "ab_report_for", "default_ab_store"):
        assert hasattr(ac, name)


# === Round-trip ==========================================================

def test_ab_locate_then_best_strategy_round_trip(monkeypatch, temp_store):
    _patch_locator_resolutions(monkeypatch, {
        "image.png": (0, 0), "ocr.png": None,
    })
    for _ in range(5):
        ab_locate(
            target_id="login_btn",
            strategies={
                "image": image_locator("image.png"),
                "ocr": image_locator("ocr.png"),
            },
            store=temp_store,
        )
    winner = temp_store.report("login_btn").best_strategy()
    assert winner.strategy == "image"
