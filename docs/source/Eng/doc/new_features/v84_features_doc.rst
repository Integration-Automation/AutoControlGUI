W3C Baggage Propagation
=======================

``trace_context`` carries trace and span identity across an HTTP boundary, but
there was no way to propagate cross-cutting key-value context (``run_id`` /
``tenant`` / ``experiment``) alongside it. This implements the W3C Baggage
header — a percent-encoded ``key=value`` list — so a run can attach such context
to outgoing requests and read it back on the other side.

Pure standard library (``urllib.parse``); imports no ``PySide6``. ``Baggage`` is
immutable (mutators return a new instance), so propagation is deterministic.

Headless API
------------

.. code-block:: python

    from je_auto_control import Baggage, inject_baggage, extract_baggage

    bag = Baggage({"tenant": "acme"}).set("run_id", "42")
    headers = inject_baggage(outgoing_headers, bag)
    # headers["baggage"] == "tenant=acme,run_id=42"

    received = extract_baggage(request_headers)
    tenant = received.get("tenant")

``Baggage`` wraps an immutable key-value map: ``get`` reads, ``set`` / ``remove``
return new instances, and ``to_dict`` exports the entries. ``parse_baggage``
reads the header (dropping optional ``;metadata`` and rejecting empty keys),
``format_baggage`` percent-encodes keys and values back into a header value,
and ``inject_baggage`` / ``extract_baggage`` write and read the ``baggage``
header on a request dict (extraction is case-insensitive). Pairs naturally with
``trace_context`` to carry context alongside the trace.

Executor commands
-----------------

``AC_baggage_parse`` parses a ``header`` into ``{items}``; ``AC_baggage_format``
serialises an ``items`` object into ``{header}``. Both are exposed as MCP tools
(``ac_baggage_parse`` / ``ac_baggage_format``) and as Script Builder commands
under **Data**.
