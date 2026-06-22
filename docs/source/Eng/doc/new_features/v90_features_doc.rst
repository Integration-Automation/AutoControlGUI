HTTP Content Negotiation & Decompression
========================================

``urllib`` / ``http_request`` never sets ``Accept-Encoding`` and never decodes a
``Content-Encoding`` response, so a body from a server that compresses arrives
raw; there was also no quality-value parser. This adds ``Accept`` /
``Accept-Encoding`` builders, a q-value parser, and gzip / deflate decoding.

Pure standard library (``gzip`` / ``zlib``); imports no ``PySide6``. Brotli is
deliberately excluded (not stdlib). Every function is pure, so it is fully
deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        build_accept, build_accept_encoding, negotiated_call,
        parse_quality_values, decode_body, build_call,
    )

    call = negotiated_call(
        build_call(url),
        accept=build_accept([("application/json", 1.0), ("text/html", 0.8)]),
        accept_encoding=build_accept_encoding(),
    )
    # ... perform the call, then:
    body = decode_body(response["headers"], raw_bytes)

    ranked = parse_quality_values("text/html;q=0.8, application/json")
    # [("application/json", 1.0), ("text/html", 0.8)]

``build_accept`` turns media types or ``(type, q)`` pairs into an ``Accept``
header; ``build_accept_encoding`` defaults to ``gzip, deflate``.
``parse_quality_values`` parses an ``Accept`` / ``Accept-Encoding`` header into
``(token, q)`` pairs sorted by quality (ties keep their order). ``decode_body``
decompresses a response body according to its ``Content-Encoding`` (``gzip`` /
``deflate``, including raw deflate, plus ``identity``), raising ``ValueError``
for anything unsupported. ``negotiated_call`` adds the negotiation headers to a
``build_call`` dict.

Executor commands
-----------------

``AC_decode_body`` decodes a base64 ``body_base64`` per its ``headers`` and
returns ``{body_base64, text}``; ``AC_parse_quality_values`` returns
``{values}``. Both are exposed as MCP tools (``ac_decode_body`` /
``ac_parse_quality_values``) and as Script Builder commands under **Data**.
