OTLP/JSON Span Export
=====================

``agent_trace.to_otel`` returns flat span dicts that are not valid OTLP/JSON
(no ``resourceSpans`` / ``scopeSpans`` nesting, no proper attribute encoding,
times not as uint64 strings). This shapes a list of spans into the envelope an
OpenTelemetry collector ingests directly via its file exporter.

Pure standard library (``json``); imports no ``PySide6``. Times are supplied by
the caller (no wall clock), so the envelope is byte-stable and CI-testable.

Headless API
------------

.. code-block:: python

    from je_auto_control import spans_to_otlp, write_otlp

    spans = [{
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": "00f067aa0ba902b7",
        "name": "run_suite",
        "start_unix_nano": started_ns, "end_unix_nano": ended_ns,
        "attributes": {"ok": True, "cases": 12},
    }]
    payload = spans_to_otlp(spans, resource_attrs={"service.name": "autocontrol"})
    write_otlp(payload, "trace.otlp.json")

``spans_to_otlp`` wraps spans in the ``resourceSpans → scopeSpans → spans``
structure: trace/span IDs stay hex, times become uint64 strings, and attributes
are encoded as OTLP ``KeyValue`` entries (``stringValue`` / ``intValue`` /
``boolValue`` / ``doubleValue``). ``attributes_to_otlp`` exposes that attribute
conversion, and ``write_otlp`` writes the payload as JSON. The result is what an
OpenTelemetry collector's file exporter reads — pairing with ``trace_context``
for the IDs and ``agent_trace`` for the span data.

Executor command
----------------

``AC_spans_to_otlp`` wraps ``spans`` (with optional ``resource_attrs``) into
``{payload}``. It is exposed as the MCP tool ``ac_spans_to_otlp`` and as a
Script Builder command under **Report**.
