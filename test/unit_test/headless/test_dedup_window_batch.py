"""Headless tests for the time-windowed dedup inbox. Pure stdlib, no Qt."""
import je_auto_control as ac
from je_auto_control.utils.dedup_window import DedupWindow


def test_check_and_mark_first_then_duplicate():
    window = DedupWindow(60, clock=lambda: 1000.0)
    assert window.check_and_mark("m1") is True       # first
    assert window.check_and_mark("m1") is False      # duplicate
    assert window.check_and_mark("m2") is True


def test_seen_and_mark():
    now = [0.0]
    window = DedupWindow(10, clock=lambda: now[0])
    assert window.seen("x") is False
    window.mark("x")
    assert window.seen("x") is True


def test_ttl_eviction():
    now = [100.0]
    window = DedupWindow(10, clock=lambda: now[0])
    window.mark("x")
    assert window.seen("x") is True
    now[0] += 20                                     # past TTL
    assert window.seen("x") is False
    assert window.check_and_mark("x") is True        # re-allowed after expiry


def test_size_counts_live_only():
    now = [0.0]
    window = DedupWindow(5, clock=lambda: now[0])
    window.mark("a")
    window.mark("b")
    assert window.size() == 2
    now[0] += 10
    assert window.size() == 0


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    name = "dedup-exec-test"
    rec = ac.execute_action([[
        "AC_dedup_check", {"name": name, "message_id": "e1"}]])
    assert next(v for v in rec.values()
                if isinstance(v, dict))["first_seen"] is True
    rec2 = ac.execute_action([[
        "AC_dedup_check", {"name": name, "message_id": "e1"}]])
    assert next(v for v in rec2.values()
                if isinstance(v, dict))["first_seen"] is False


def test_wiring():
    assert "AC_dedup_check" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_dedup_check" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_dedup_check" in {s.command for s in _build_specs()}


def test_facade_exports():
    assert hasattr(ac, "DedupWindow") and "DedupWindow" in ac.__all__
