Cookie Jar (HTTP Session Carry)
===============================

``http_request`` is stateless — no session cookies persist across calls, so a
login-then-call REST flow could not carry a session headlessly. This parses
``Set-Cookie`` response headers into a jar and builds the ``Cookie`` request
header; the jar is JSON-serialisable so a session can be saved and reloaded.

Pure standard library (``json``); imports no ``PySide6``. The jar is a simple
in-memory name-value store (cookies cleared on ``Max-Age<=0`` / empty value),
so behaviour is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import CookieJar, parse_set_cookie

    jar = CookieJar()
    jar.update(login_response_set_cookie_headers)   # str or list of Set-Cookie
    cookie = jar.cookie_header()                     # "sid=abc; theme=dark"
    # send `cookie` as the Cookie header on subsequent requests

    jar.save("session.json")
    jar = CookieJar.load("session.json")

``parse_set_cookie`` parses one ``Set-Cookie`` value into ``{name, value,
attributes}``. ``CookieJar.update`` applies one or many ``Set-Cookie`` headers
(removing a cookie on an empty value or ``Max-Age<=0``); ``set`` assigns
directly; ``cookie_header`` builds the request header; ``to_dict`` / ``from_dict``
and ``save`` / ``load`` persist the jar as JSON. (Domain/path matching is
simplified — this is a session-carry jar, not a full RFC 6265 policy engine.)

Executor commands
-----------------

``AC_cookie_header`` builds ``{cookie_header, cookies}`` from one or many
``set_cookies``; ``AC_parse_set_cookie`` returns ``{cookie}`` for one header.
Both are exposed as MCP tools (``ac_cookie_header`` / ``ac_parse_set_cookie``)
and as Script Builder commands under **Data**.
