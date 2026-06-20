Outbound CloudEvents Emitter
============================

AutoControl can *receive* webhooks but had no way to *emit* events outbound.
CloudEvents 1.0 (CNCF) is the interop standard for event payloads — Knative,
Azure Event Grid, iPaaS, and generic webhook consumers all speak it. This wraps
run-lifecycle / assertion / failure data in a CloudEvents envelope and
(optionally) POSTs it over the HTTP binding, reusing the framework's egress
allowlist guard.

The transport is injectable (a ``sink`` / ``poster`` callable), so emission is
unit-testable with no network. Pure standard library; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import to_cloudevent, post_cloudevent, EventEmitter

    event = to_cloudevent("com.example.run.finished", "/runs/42",
                          {"status": "passed"}, subject="run-42")
    # -> {specversion, id, source, type, time, datacontenttype, subject, data}

    post_cloudevent("https://hooks.example.com/ce", event)   # egress-guarded POST

    emitter = EventEmitter(source="je_auto_control")
    emitter.emit("run.started", {"flow": "checkout"})
    emitter.events                                           # captured envelopes

``to_cloudevent`` fills ``specversion`` / ``id`` (a fresh UUID) / ``time`` (now,
UTC) automatically; pass ``event_id`` / ``time`` to override. ``EventEmitter``
binds a fixed ``source`` and dispatches each envelope to a ``sink`` (an in-memory
log by default — inject your own to forward to a bus). ``post_cloudevent``
accepts a ``poster`` to inject a transport in tests.

Executor command
----------------

``AC_emit_event`` takes ``event_type`` (+ optional ``data`` / ``source`` /
``subject`` / ``url``); it returns ``{event}`` and, when ``url`` is given,
``{event, status}`` after POSTing. The same operation is exposed as the MCP tool
``ac_emit_event`` and as a Script Builder command under **Tools**.
