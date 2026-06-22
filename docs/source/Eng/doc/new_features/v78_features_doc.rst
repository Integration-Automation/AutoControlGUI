RFC 9457 Problem Details Parsing
================================

``http_request`` returns a non-2xx body unparsed, so a flow — or
``assert_http`` — had no structured way to read a standardised API error.
This parses the RFC 9457 ``application/problem+json`` document: the registered
``type`` / ``title`` / ``status`` / ``detail`` / ``instance`` members plus any
vendor extensions.

Pure standard library (``json``); imports no ``PySide6``. Every function is
pure (response dict in, dataclass out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import http_request, parse_problem, raise_for_problem

    response = http_request("https://api.example.com/orders/12")
    problem = parse_problem(response)        # None unless problem+json
    if problem is not None:
        log(problem.status, problem.title, problem.detail)
        retry_after = problem.extensions.get("balance")

    # or convert a problem response into an exception:
    raise_for_problem(response)              # raises HttpProblemError

``is_problem`` checks the ``Content-Type`` (case-insensitively).
``parse_problem`` returns a ``ProblemDetails`` (``type`` defaulting to
``about:blank``, an integer ``status`` when coercible, and all non-registered
keys collected into ``extensions``) or ``None`` when the response is not a
problem document; it falls back to parsing ``text`` when ``json`` is absent.
``ProblemDetails.summary`` gives a one-line description and ``to_dict`` flattens
the document with extensions merged back in. ``raise_for_problem`` raises
``HttpProblemError`` (carrying the ``ProblemDetails``) for a problem response
and does nothing otherwise.

Executor command
----------------

``AC_parse_problem`` takes an ``http_request`` ``response`` and returns
``{problem}`` (the flattened document) or ``null``. It is exposed as the MCP
tool ``ac_parse_problem`` and as a Script Builder command under **Data**.
