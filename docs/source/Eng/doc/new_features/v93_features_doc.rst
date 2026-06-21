Canonical Log Lines & Structured Logging
========================================

``logging_instance`` emits a fixed pipe-delimited human string with no JSON
option and no trace/span fields, but OTel log-trace correlation needs
``trace_id`` / ``span_id`` on each record. This adds a Stripe-style canonical
log line (one wide field-bag emitted per run) and a JSON ``logging.Formatter``
that carries trace context.

Pure standard library (``json`` / ``logging``); imports no ``PySide6``. The
timer clock is injectable, so durations are deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        CanonicalLogLine, bind_trace_context, JSONLogFormatter,
        new_root_context,
    )

    line = CanonicalLogLine({"event": "run_suite"})
    bind_trace_context(line, new_root_context())
    with line.timer("execute"):
        run()
    line.add("ok", True).emit(logger.info)         # one wide line per run

    # structured logging with trace correlation:
    handler.setFormatter(JSONLogFormatter())

``CanonicalLogLine`` accumulates request-scoped fields (``add`` / ``update``),
times a block into ``{name}_ms`` via ``timer`` (injectable clock), and
``render`` / ``emit`` the wide line as JSON. ``bind_trace_context`` attaches a
``SpanContext``'s ``trace_id`` / ``span_id``. ``JSONLogFormatter`` is a
``logging.Formatter`` that emits one JSON object per record including
``trace_id`` / ``span_id`` and any ``extra=`` fields — the log-trace correlation
counterpart to ``trace_context``.

Executor command
----------------

``AC_canonical_log`` builds a canonical line from a ``fields`` object and returns
``{line, json}``. It is exposed as the MCP tool ``ac_canonical_log`` and as a
Script Builder command under **Report**.
