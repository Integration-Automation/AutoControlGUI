"""Headless tests for OTLP/JSON span export. Pure stdlib, no Qt."""
import json
from pathlib import Path

import je_auto_control as ac
from je_auto_control.utils.otlp_export import (
    attributes_to_otlp, spans_to_otlp, write_otlp,
)

_SPAN = {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
    "parent_span_id": "00f067aa0ba902b8",
    "name": "execute",
    "start_unix_nano": 1700000000000000000,
    "end_unix_nano": 1700000000500000000,
    "attributes": {"ok": True, "count": 3, "ratio": 0.5, "label": "x"},
}


def test_attributes_to_otlp_typing():
    attrs = {a["key"]: a["value"] for a in
             attributes_to_otlp({"s": "v", "i": 7, "b": True, "d": 1.5})}
    assert attrs["s"] == {"stringValue": "v"}
    assert attrs["i"] == {"intValue": "7"}       # int64 as string
    assert attrs["b"] == {"boolValue": True}
    assert attrs["d"] == {"doubleValue": 1.5}


def test_spans_to_otlp_envelope_shape():
    payload = spans_to_otlp([_SPAN],
                            resource_attrs={"service.name": "autocontrol"})
    resource_spans = payload["resourceSpans"][0]
    assert resource_spans["resource"]["attributes"][0]["key"] == "service.name"
    scope_spans = resource_spans["scopeSpans"][0]
    assert scope_spans["scope"]["name"] == "je_auto_control"
    span = scope_spans["spans"][0]
    assert span["traceId"] == _SPAN["trace_id"]
    assert span["spanId"] == _SPAN["span_id"]
    assert span["parentSpanId"] == _SPAN["parent_span_id"]
    assert span["startTimeUnixNano"] == "1700000000000000000"   # uint64 string
    assert span["kind"] == 1


def test_span_without_parent_omits_field():
    span = dict(_SPAN)
    del span["parent_span_id"]
    out = spans_to_otlp([span])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert "parentSpanId" not in out


def test_scope_version_included_when_set():
    payload = spans_to_otlp([], scope_version="1.2.3")
    assert payload["resourceSpans"][0]["scopeSpans"][0]["scope"]["version"] == \
        "1.2.3"


def test_write_otlp(tmp_path):
    path = write_otlp(spans_to_otlp([_SPAN]), str(tmp_path / "trace.json"))
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "resourceSpans" in loaded


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_spans_to_otlp", {"spans": json.dumps([_SPAN])}]])
    payload = next(v for v in rec.values() if isinstance(v, dict))["payload"]
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["name"] == "execute"


def test_wiring():
    assert "AC_spans_to_otlp" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_spans_to_otlp" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_spans_to_otlp" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("attributes_to_otlp", "spans_to_otlp", "write_otlp"):
        assert hasattr(ac, attr) and attr in ac.__all__
