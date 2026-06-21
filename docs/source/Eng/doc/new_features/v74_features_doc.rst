Bulkhead & Rate-Limit Headers
=============================

``resilience`` recovers from failures and ``rate_limit`` paces calls, but
nothing capped the number of *simultaneous* in-flight calls to one resource
(so a slow dependency could exhaust every worker), and the HTTP client read
``Retry-After`` / ``RateLimit-*`` response headers but honored none of them.
This adds a bulkhead (bounded-concurrency permit with load-shedding) and a
parser for the server's advised delay.

Pure standard library (``threading`` + ``email.utils``); the permit counting is
non-blocking (reject when full), so it is deterministic and CI-testable without
spawning threads. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import Bulkhead, BulkheadFullError, next_delay

    payments = Bulkhead(max_concurrent=4, name="payments")
    try:
        result = payments.run(call_payment_api, order)
    except BulkheadFullError:
        defer(order)               # shed load instead of piling on

    # honor the server's back-off after an HTTP call
    wait = next_delay(response)     # from Retry-After / RateLimit-* headers
    if wait:
        sleep(wait)

``Bulkhead`` caps simultaneous holders to ``max_concurrent`` — ``try_enter`` /
``release``, a context manager, and ``run(func)`` all reject (``BulkheadFullError``)
when full, isolating one slow dependency from exhausting the rest.
``parse_retry_after`` understands both the delta-seconds and HTTP-date forms;
``parse_ratelimit`` reads the ``RateLimit-Limit/Remaining/Reset`` convention;
``next_delay`` combines them into the wait a flow should observe after a
``429`` / ``503``.

Executor commands
-----------------

``AC_bulkhead_run`` runs an ``actions`` list under a named bulkhead (``name``,
``max_concurrent``) and returns ``{entered, in_flight, record?}``.
``AC_retry_after`` takes an HTTP ``response`` (``{status, headers}``) and returns
``{delay}``. Both are exposed as MCP tools (``ac_bulkhead_run`` /
``ac_retry_after``) and as Script Builder commands under **Flow**.
