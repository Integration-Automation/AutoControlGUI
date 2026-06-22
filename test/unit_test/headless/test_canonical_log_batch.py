"""Headless tests for canonical log lines + JSON formatting. No Qt."""
import json
import logging

import pytest

import je_auto_control as ac
from je_auto_control.utils.canonical_log import (
    CanonicalLogLine, JSONLogFormatter, bind_trace_context,
)


def test_add_update_and_render():
    line = CanonicalLogLine({"event": "run"}).add("ok", True).update({"n": 3})
    assert line.to_dict() == {"event": "run", "ok": True, "n": 3}
    assert json.loads(line.render()) == {"event": "run", "ok": True, "n": 3}


def test_timer_uses_injected_clock():
    ticks = iter([10.0, 10.5])
    line = CanonicalLogLine(clock=lambda: next(ticks))
    with line.timer("step"):
        pass
    assert line.to_dict()["step_ms"] == pytest.approx(500.0)


def test_emit_to_sink():
    captured = []
    CanonicalLogLine({"a": 1}).emit(captured.append)
    assert captured == [{"a": 1}]


def test_bind_trace_context():
    class _Ctx:
        trace_id = "t" * 32
        span_id = "s" * 16
    line = bind_trace_context(CanonicalLogLine(), _Ctx())
    assert line.to_dict()["trace_id"] == "t" * 32
    assert line.to_dict()["span_id"] == "s" * 16


def test_json_log_formatter_includes_extras():
    formatter = JSONLogFormatter()
    record = logging.makeLogRecord(
        {"name": "x", "levelname": "INFO", "msg": "hi",
         "trace_id": "abc", "custom": 5})
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "hi" and payload["level"] == "INFO"
    assert payload["trace_id"] == "abc" and payload["custom"] == 5


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_canonical_log", {"fields": json.dumps({"event": "run", "ok": True})}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["line"] == {"event": "run", "ok": True}
    assert json.loads(out["json"]) == {"event": "run", "ok": True}


def test_wiring():
    assert "AC_canonical_log" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_canonical_log" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_canonical_log" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("CanonicalLogLine", "JSONLogFormatter", "bind_trace_context"):
        assert hasattr(ac, attr) and attr in ac.__all__
