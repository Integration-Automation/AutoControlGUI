Agent Observability (GenAI OpenTelemetry Spans)
===============================================

When automation drives an LLM agent, you want the same observability an
OpenTelemetry backend gives a service: per-operation spans carrying token usage,
model, and status. ``AgentTrace`` records spans whose attributes follow the
OpenTelemetry **GenAI semantic conventions** — ``gen_ai.operation.name``,
``gen_ai.system``, ``gen_ai.request.model``, ``gen_ai.usage.input_tokens`` /
``gen_ai.usage.output_tokens``, ``gen_ai.tool.name`` — and the convention span
name ``"{operation} {model}"``. :meth:`AgentTrace.to_otel` output drops straight
into an OTLP exporter, while :meth:`AgentTrace.summary` rolls up cost and latency
for a run.

It pairs with :doc:`trajectory evaluation <v36_features_doc>` — record the run
here, score it there. Pure standard library (no ``opentelemetry`` dependency);
the clock is injectable so durations are deterministically testable. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import AgentTrace

    trace = AgentTrace()
    # one-shot record of a completed call:
    trace.record("chat", model="claude-opus-4-8", system="anthropic",
                 input_tokens=1200, output_tokens=180, duration_s=0.9)

    # or time a live block; set token counts on the yielded dict:
    with trace.operation("tool", tool_name="search") as fields:
        result = run_tool()
        fields["output_tokens"] = 42        # error inside marks the span error

    print(trace.summary())   # {span_count, error_count, input_tokens, ...}
    exporter.export(trace.to_otel())        # OTLP-friendly span dicts

``summary`` aggregates ``span_count``, ``error_count``, ``input_tokens``,
``output_tokens``, and total ``duration_s``. ``to_otel`` returns each span as
``{name, kind, attributes, duration_s, status:{code}}`` with an OTel status code.

Executor commands
-----------------

A module-level default trace backs the executor/MCP surfaces so a flow can build
a trace across steps:

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_trace_record``              Record a GenAI span (operation/model/tokens/…).
``AC_trace_summary``             Roll up the default trace.
``AC_trace_export``              Export the default trace as OTLP spans.
``AC_trace_reset``               Clear the default trace.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_trace_record`` /
``ac_trace_summary`` / ``ac_trace_export`` / ``ac_trace_reset``) and as Script
Builder commands under **Agent**.
