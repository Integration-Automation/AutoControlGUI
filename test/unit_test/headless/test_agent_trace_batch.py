"""Headless tests for GenAI-convention agent tracing. The clock is injected,
so durations are deterministic. Pure stdlib, no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.agent_trace import AgentTrace


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_record_uses_genai_conventions():
    trace = AgentTrace()
    span = trace.record("chat", model="claude-opus-4-8", system="anthropic",
                        input_tokens=100, output_tokens=20)
    assert span["name"] == "chat claude-opus-4-8"
    attrs = span["attributes"]
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == "claude-opus-4-8"
    assert attrs["gen_ai.usage.input_tokens"] == 100
    assert attrs["gen_ai.usage.output_tokens"] == 20


def test_summary_aggregates_tokens_and_errors():
    trace = AgentTrace()
    trace.record("chat", model="m", input_tokens=10, output_tokens=5)
    trace.record("chat", model="m", input_tokens=7, output_tokens=3)
    trace.record("tool", tool_name="search", status="error")
    summary = trace.summary()
    assert summary["span_count"] == 3
    assert summary["error_count"] == 1
    assert summary["input_tokens"] == 17
    assert summary["output_tokens"] == 8


def test_operation_context_times_and_records():
    clock = _Clock()
    trace = AgentTrace(clock=clock)
    with trace.operation("chat", model="m") as fields:
        clock.now += 2.5
        fields["output_tokens"] = 42
    span = trace.spans()[0]
    assert span["duration_s"] == pytest.approx(2.5)
    assert span["status"] == "ok"
    assert span["attributes"]["gen_ai.usage.output_tokens"] == 42


def test_operation_marks_error_on_exception():
    trace = AgentTrace(clock=_Clock())
    with pytest.raises(ValueError):
        with trace.operation("tool", tool_name="x"):
            raise ValueError("boom")
    span = trace.spans()[0]
    assert span["status"] == "error"
    assert span["attributes"]["gen_ai.tool.name"] == "x"


def test_to_otel_shape():
    trace = AgentTrace()
    trace.record("chat", model="m", status="error")
    otel = trace.to_otel()
    assert otel[0]["kind"] == "CLIENT"
    assert otel[0]["status"]["code"] == "ERROR"
    assert otel[0]["attributes"]["gen_ai.operation.name"] == "chat"


def test_reset_clears():
    trace = AgentTrace()
    trace.record("chat")
    trace.reset()
    assert trace.spans() == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    ac.execute_action([["AC_trace_reset", {}]])
    ac.execute_action([[
        "AC_trace_record",
        {"operation": "chat", "model": "m", "input_tokens": 5,
         "output_tokens": 2},
    ]])
    rec = ac.execute_action([["AC_trace_summary", {}]])
    summary = next(v for v in rec.values() if isinstance(v, dict))
    assert summary["span_count"] == 1
    assert summary["input_tokens"] == 5
    ac.execute_action([["AC_trace_reset", {}]])     # leave global state clean


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_trace_record", "AC_trace_summary", "AC_trace_export",
            "AC_trace_reset"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_trace_record", "ac_trace_summary", "ac_trace_export",
            "ac_trace_reset"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_trace_record", "AC_trace_summary", "AC_trace_export",
            "AC_trace_reset"} <= cmds


def test_facade_exports():
    for attr in ("AgentTrace", "default_trace", "reset_trace"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
