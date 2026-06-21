W3C Trace Context Propagation
=============================

The ``observability`` tracer and ``agent_trace`` spans carry no IDs, so a span
on one side of an HTTP call could not be correlated with the work it triggered
on the other. This adds the W3C Trace Context standard — generate, parse, and
propagate ``traceparent`` / ``tracestate`` headers so spans, logs, and
downstream services all share one trace and span lineage.

Pure standard library (``os`` / ``re``); imports no ``PySide6``. ID generation
takes an injectable RNG, so trace and span IDs are deterministic under test.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        new_root_context, child_context, inject_context, extract_context,
        parse_traceparent, format_traceparent,
    )

    # Start a trace and propagate it onto an outgoing request:
    ctx = new_root_context()
    headers = inject_context({"accept": "application/json"}, ctx)
    # headers["traceparent"] == "00-<32 hex>-<16 hex>-01"

    # On the receiving side, continue the same trace:
    parent = extract_context(request_headers)
    if parent is not None:
        span = child_context(parent)        # same trace_id, new span_id

``SpanContext`` is the immutable (``trace_id``, ``span_id``, ``trace_flags``,
``tracestate``) tuple. ``new_root_context`` mints a fresh trace; ``child_context``
keeps the trace id and inherited state but allocates a new span id.
``parse_traceparent`` / ``format_traceparent`` round-trip the version-``00``
header (rejecting bad versions, malformed or all-zero IDs with
``TraceContextError``); ``parse_tracestate`` / ``format_tracestate`` handle the
vendor list. ``inject_context`` writes the headers; ``extract_context`` reads
them back (case-insensitively).

Executor commands
-----------------

``AC_trace_inject`` propagates a context onto outgoing ``headers`` — with a
``traceparent`` it derives a child of that parent, otherwise it starts a fresh
root — and returns ``{headers, traceparent, trace_id, span_id}``.
``AC_trace_extract`` reads a context back out of request ``headers`` and returns
``{context}`` (or ``null`` when no ``traceparent`` is present). Both are exposed
as MCP tools (``ac_trace_inject`` / ``ac_trace_extract``) and as Script Builder
commands under **Data**.
