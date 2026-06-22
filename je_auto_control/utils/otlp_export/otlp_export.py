"""Render spans into the OTLP/JSON ``resourceSpans`` envelope.

``agent_trace.to_otel`` returns flat span dicts that are not valid OTLP/JSON
(no ``resourceSpans`` / ``scopeSpans`` nesting, no proper attribute encoding,
times not as uint64 strings). This shapes a list of spans into the envelope an
OpenTelemetry collector ingests directly via its file exporter.

Pure standard library (``json``); imports no ``PySide6``. Times are supplied by
the caller (no wall clock), so the envelope is byte-stable and CI-testable.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


def _attr_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}        # int64 encoded as string
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def attributes_to_otlp(attributes: Optional[Mapping[str, Any]]
                       ) -> List[Dict[str, Any]]:
    """Convert a plain attribute dict to an OTLP KeyValue list."""
    return [{"key": str(key), "value": _attr_value(value)}
            for key, value in (attributes or {}).items()]


def _span_to_otlp(span: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "traceId": span["trace_id"],
        "spanId": span["span_id"],
        "name": span.get("name", ""),
        "kind": int(span.get("kind", 1)),
        "startTimeUnixNano": str(span.get("start_unix_nano", 0)),
        "endTimeUnixNano": str(span.get("end_unix_nano", 0)),
        "attributes": attributes_to_otlp(span.get("attributes")),
    }
    if span.get("parent_span_id"):
        out["parentSpanId"] = span["parent_span_id"]
    return out


def spans_to_otlp(spans: Sequence[Mapping[str, Any]], *,
                  resource_attrs: Optional[Mapping[str, Any]] = None,
                  scope_name: str = "je_auto_control",
                  scope_version: str = "") -> Dict[str, Any]:
    """Wrap ``spans`` in an OTLP/JSON ``resourceSpans`` envelope.

    Each span is a dict with ``trace_id`` / ``span_id`` (hex), ``name``,
    ``start_unix_nano`` / ``end_unix_nano`` and optional ``attributes`` /
    ``parent_span_id`` / ``kind``.
    """
    scope: Dict[str, Any] = {"name": scope_name}
    if scope_version:
        scope["version"] = scope_version
    return {"resourceSpans": [{
        "resource": {"attributes": attributes_to_otlp(resource_attrs)},
        "scopeSpans": [{
            "scope": scope,
            "spans": [_span_to_otlp(span) for span in spans],
        }],
    }]}


def write_otlp(payload: Mapping[str, Any], path: str) -> str:
    """Write an OTLP payload to ``path`` as JSON; return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(out)
