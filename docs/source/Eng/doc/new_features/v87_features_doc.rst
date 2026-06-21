RFC 8288 Link Header & Pagination
=================================

Paginated REST APIs return ``Link: <...>; rel="next"`` headers, but nothing
parsed them, so multi-page fetches needed manual glue. This parses the header
(handling quoted parameter values and multiple links), indexes links by their
relation, and walks ``rel="next"`` over an injected transport.

Pure standard library (``re``); imports no ``PySide6``. The parser is pure and
``paginate`` takes an injected ``fetch`` callable, so pagination is CI-testable
without a live server.

Headless API
------------

.. code-block:: python

    from je_auto_control import parse_link_header, next_url, links_by_rel, paginate

    header = '<https://api/x?page=2>; rel="next", <https://api/x?page=9>; rel="last"'
    links = parse_link_header(header)            # [Link(uri=..., rel="next"), ...]
    nxt = next_url(header)                        # "https://api/x?page=2"
    last = links_by_rel(header)["last"].uri

    # Walk every page over an injected fetch (transport / cassette):
    pages = paginate(start_url, fetch, max_pages=50)

``parse_link_header`` returns a list of ``Link`` (``uri``, ``rel``, and all
``params``), tolerating quoted values that contain commas and multiple links in
one header. ``links_by_rel`` indexes by each (space-separated) relation,
``next_url`` is the ``rel="next"`` convenience, and ``paginate`` fetches a URL
and follows ``next`` links via the supplied ``fetch`` callable up to
``max_pages``.

Executor commands
-----------------

``AC_parse_link_header`` parses a header ``value`` into ``{links}``;
``AC_next_url`` returns ``{url}`` for ``rel="next"``. Both are exposed as MCP
tools (``ac_parse_link_header`` / ``ac_next_url``) and as Script Builder
commands under **Data**.
