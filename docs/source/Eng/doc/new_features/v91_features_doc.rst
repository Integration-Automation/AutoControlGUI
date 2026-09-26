Cookie Jar (HTTP Session Carry)
===============================

``http_request`` is stateless — no session cookies persist across calls, so a
login-then-call REST flow could not carry a session headlessly. This parses
``Set-Cookie`` response headers into a jar and builds the ``Cookie`` request
header; the jar is JSON-serialisable so a session can be saved and reloaded.

Pure standard library (``json``); imports no ``PySide6``. The jar is a simple
in-memory name-value store (cookies cleared on ``Max-Age<=0`` or a past ``Expires``; an empty value is kept),
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
(removing a cookie on ``Max-Age<=0`` or a past ``Expires``); ``set`` assigns
directly; ``cookie_header`` builds the request header; ``to_dict`` / ``from_dict``
and ``save`` / ``load`` persist the jar as JSON.

``Expires`` is read with the RFC 6265 5.1.1 cookie-date algorithm (two-digit
years 70-99 are 19xx and 00-69 are 20xx; an unparseable date is ignored), a
``Max-Age`` must be ASCII digits with an optional ``-``, and when an attribute
repeats, the last *valid* one decides (``Max-Age`` over ``Expires``). A header
with a control character other than tab is ignored whole.

The jar ignores ``Domain``, ``Path`` and ``Secure``: every stored cookie goes
into every ``Cookie`` header it builds. It is a session-carry jar, not an
RFC 6265 policy engine, so keep **one jar per origin**; a shared jar sends one
host's cookies to every other host the flow calls.

Executor commands
-----------------

``AC_cookie_header`` builds ``{cookie_header, cookies}`` from one or many
``set_cookies``; ``AC_parse_set_cookie`` returns ``{cookie}`` for one header.
Both are exposed as MCP tools (``ac_cookie_header`` / ``ac_parse_set_cookie``)
and as Script Builder commands under **Data**.
