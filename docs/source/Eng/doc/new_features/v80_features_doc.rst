Server-Sent Events (SSE) Client Parser
======================================

The MCP HTTP transport *emits* Server-Sent Events, but nothing consumed them:
an LLM, agent, or chatops endpoint that streams ``text/event-stream`` left
``http_request`` holding a raw, unparsed blob. This implements the WHATWG
event-stream parsing algorithm — ``event`` / ``data`` / ``id`` / ``retry``
fields, comment lines, the leading-space rule, and blank-line dispatch — with
an incremental ``feed`` for streamed chunks.

Pure standard library (``re``); imports no ``PySide6``. The parser is pure and
fully deterministic, so streaming logic is CI-testable without a live server.

Headless API
------------

.. code-block:: python

    from je_auto_control import parse_event_stream, SSEParser

    # Parse a complete response body:
    for event in parse_event_stream(response_text):
        handle(event.event, event.data, event.id)

    # Or parse incrementally as chunks arrive:
    parser = SSEParser()
    for chunk in stream:
        for event in parser.feed(chunk):
            handle(event)
    for event in parser.close():           # flush a trailing event
        handle(event)

``SSEEvent`` is the dispatched ``(event, data, id, retry)`` tuple (``event``
defaulting to ``"message"``). ``SSEParser.feed`` buffers a partial trailing line
across calls and returns each event completed by a blank line; ``close``
flushes a final event when the stream ends without one. ``id`` and ``retry``
persist across subsequent events per the spec. ``parse_event_stream`` is the
one-shot helper for a complete blob and flushes the trailing event.

Executor command
----------------

``AC_parse_sse`` parses a ``text`` blob into ``{events}`` (each
``{event, data, id, retry}``). It is exposed as the MCP tool ``ac_parse_sse``
and as a Script Builder command under **Data**.
