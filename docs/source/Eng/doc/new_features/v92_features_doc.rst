Conditional HTTP Requests & Cache Validators
============================================

``http_request`` never sends ``If-None-Match`` / ``If-Modified-Since`` nor reads
``Cache-Control``, so every poll re-downloads an unchanged resource. This
extracts caching validators from a response, parses ``Cache-Control``, decides
freshness, and conditions the next request so the server can answer ``304 Not
Modified``.

Pure standard library; imports no ``PySide6``. Freshness takes an explicit age
(no wall clock), so the logic is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        store_validators, conditioned_call, is_fresh, is_not_modified,
        parse_cache_control, build_call,
    )

    response = http_request(url)
    validators = store_validators(response)
    if is_fresh(validators, age_seconds=now - stored_at):
        use_cached()
    else:
        revalidation = conditioned_call(build_call(url), validators)
        fresh = perform(revalidation)
        if is_not_modified(fresh):
            use_cached()           # 304 → the stored body is still valid

``store_validators`` pulls ``etag`` / ``last_modified`` / ``date`` and the parsed
``cache_control`` from a response. ``parse_cache_control`` turns the header into
a directive dict (``max-age`` as an int, flags as ``True``). ``conditioned_call``
adds ``If-None-Match`` / ``If-Modified-Since`` to a ``build_call`` dict.
``is_fresh`` reports whether a cached entry is still fresh for a given age
(``no-store`` / ``no-cache`` are never fresh). ``is_not_modified`` detects a
``304`` response.

Executor commands
-----------------

``AC_parse_cache_control`` returns ``{directives}`` for ``headers``;
``AC_store_validators`` returns ``{validators}`` for a ``response``. Both are
exposed as MCP tools (``ac_parse_cache_control`` / ``ac_store_validators``) and
as Script Builder commands under **Data**.
