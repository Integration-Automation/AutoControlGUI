HTTP Record & Replay Cassette
=============================

The HTTP client hardcoded its ``urllib`` transport, so a flow that drives a
real API could not be re-run in CI without the live server reachable. The
client now exposes a ``build_call`` / ``urllib_transport`` seam, and this layer
adds a VCR-style **cassette**: replay returns a recorded response for a
matching request (pure, no network — the CI-valuable half), while recording is
a thin pass-through over a live transport.

Pure standard library (``json``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import Cassette, CassetteMissError
    from je_auto_control.utils.http_client import build_call, urllib_transport

    # Record once (against the live server), then save:
    cassette = Cassette()
    transport = cassette.recording_transport(urllib_transport)
    transport(build_call("https://api.example.com/users/1", "GET"))
    cassette.save("users.cassette.json")

    # Replay forever — deterministic, offline:
    cassette = Cassette.load("users.cassette.json")
    response = cassette.replay(build_call("https://api.example.com/users/1", "GET"))
    assert response["status"] == 200

``build_call`` turns request parameters into a plain dict (url, method, headers,
body, timeout) without touching the network; ``urllib_transport`` performs it.
``Cassette.record`` stores one request/response pair; ``replay`` returns the
recorded response for a request matching ``match_on`` (``("method", "url")`` by
default, optionally ``"body"``) and raises ``CassetteMissError`` when nothing
matches. ``replay_transport`` / ``recording_transport`` return drop-in
transports so existing call sites swap live traffic for the cassette unchanged.

Executor command
----------------

``AC_http_replay`` takes a ``cassette`` (interactions list or ``{interactions}``,
JSON string accepted), a ``url`` and optional ``method``, and returns the
recorded ``{response}`` with no network access. It is exposed as the MCP tool
``ac_http_replay`` and as a Script Builder command under **Data**.
