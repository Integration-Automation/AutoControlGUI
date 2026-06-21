"""Headless tests for W3C Trace Context propagation. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.trace_context import (
    SpanContext, TraceContextError, child_context, extract_context,
    format_traceparent, inject_context, new_root_context, parse_traceparent,
    parse_tracestate,
)


def _seeded_rng():
    # deterministic byte source for reproducible IDs (no `random` module)
    import itertools
    counter = itertools.count(1)
    return lambda n: bytes(next(counter) % 256 for _ in range(n))


def test_roundtrip_parse_format():
    header = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    ctx = parse_traceparent(header)
    assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx.span_id == "00f067aa0ba902b7"
    assert ctx.sampled is True
    assert format_traceparent(ctx) == header


def test_new_root_is_deterministic_with_injected_rng():
    rng = _seeded_rng()
    ctx = new_root_context(rng)
    again = new_root_context(_seeded_rng())
    assert ctx.trace_id == again.trace_id and ctx.span_id == again.span_id
    assert len(ctx.trace_id) == 32 and len(ctx.span_id) == 16


def test_child_keeps_trace_changes_span():
    parent = new_root_context(_seeded_rng())
    child = child_context(parent)
    assert child.trace_id == parent.trace_id    # same trace
    assert child.span_id != parent.span_id      # new span
    assert child.trace_flags == parent.trace_flags


@pytest.mark.parametrize("bad", [
    "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7",   # 3 fields
    "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",  # version
    "00-00000000000000000000000000000000-00f067aa0ba902b7-01",  # zero trace
    "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",  # zero span
    "00-zz-00f067aa0ba902b7-01",                                # non-hex
])
def test_invalid_traceparent_raises(bad):
    with pytest.raises(TraceContextError):
        parse_traceparent(bad)


def test_tracestate_parse_and_inject():
    state = parse_tracestate("rojo=00f067aa0ba902b7,congo=t61rcWkgMzE")
    assert state == [("rojo", "00f067aa0ba902b7"), ("congo", "t61rcWkgMzE")]
    ctx = SpanContext("4bf92f3577b34da6a3ce929d0e0e4736",
                      "00f067aa0ba902b7", 1, state)
    headers = inject_context({"accept": "application/json"}, ctx)
    assert headers["tracestate"] == "rojo=00f067aa0ba902b7,congo=t61rcWkgMzE"
    assert headers["accept"] == "application/json"


def test_extract_is_case_insensitive_and_roundtrips():
    ctx = new_root_context(_seeded_rng())
    headers = inject_context({}, ctx)
    extracted = extract_context({"TraceParent": headers["traceparent"]})
    assert extracted.trace_id == ctx.trace_id
    assert extract_context({"x": "y"}) is None


# --- wiring ---------------------------------------------------------------

def test_executor_inject_then_extract():
    rec = ac.execute_action([["AC_trace_inject", {}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["trace_id"] and out["headers"]["traceparent"]
    rec2 = ac.execute_action([[
        "AC_trace_extract",
        {"headers": json.dumps(out["headers"])},
    ]])
    ctx = next(v for v in rec2.values() if isinstance(v, dict))["context"]
    assert ctx["trace_id"] == out["trace_id"]


def test_executor_child_of_parent():
    parent = format_traceparent(new_root_context())
    rec = ac.execute_action([[
        "AC_trace_inject", {"traceparent": parent}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["trace_id"] == parent.split("-")[1]   # same trace
    assert out["span_id"] != parent.split("-")[2]     # new span


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_trace_inject", "AC_trace_extract"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_trace_inject", "ac_trace_extract"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_trace_inject", "AC_trace_extract"} <= specs


def test_facade_exports():
    for attr in ("SpanContext", "TraceContextError", "new_root_context",
                 "parse_traceparent", "inject_context", "extract_context"):
        assert hasattr(ac, attr) and attr in ac.__all__
