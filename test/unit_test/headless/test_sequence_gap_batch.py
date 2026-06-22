"""Headless tests for per-stream sequence-gap detection. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.sequence_gap import SequenceTracker


def test_in_order_is_ok():
    t = SequenceTracker()
    assert t.observe("s", 1)["status"] == "ok"
    assert t.observe("s", 2)["status"] == "ok"
    assert t.observe("s", 3)["status"] == "ok"
    assert t.gaps("s") == [] and t.high_water("s") == 3


def test_gap_detected_and_filled_by_reorder():
    t = SequenceTracker()
    t.observe("s", 1)
    result = t.observe("s", 4)               # skipped 2, 3
    assert result["status"] == "gap" and result["missing"] == [2, 3]
    assert t.observe("s", 3)["status"] == "reorder"
    assert t.gaps("s") == [2]                # 3 filled, 2 still missing
    t.observe("s", 2)
    assert t.gaps("s") == []


def test_duplicate():
    t = SequenceTracker()
    t.observe("s", 1)
    t.observe("s", 2)
    assert t.observe("s", 2)["status"] == "duplicate"


def test_streams_are_independent():
    t = SequenceTracker()
    t.observe("a", 5)
    assert t.observe("b", 1)["status"] == "ok"      # first on stream b
    assert t.high_water("a") == 5 and t.high_water("b") == 1


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    name = "seq-exec-test"
    ac.execute_action([[
        "AC_sequence_observe", {"name": name, "stream_id": "s", "seq": 1}]])
    rec = ac.execute_action([[
        "AC_sequence_observe", {"name": name, "stream_id": "s", "seq": 5}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["status"] == "gap" and out["missing"] == [2, 3, 4]


def test_wiring():
    assert "AC_sequence_observe" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_sequence_observe" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_sequence_observe" in {s.command for s in _build_specs()}


def test_facade_exports():
    assert hasattr(ac, "SequenceTracker") and "SequenceTracker" in ac.__all__
