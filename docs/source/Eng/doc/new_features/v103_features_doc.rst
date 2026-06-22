Idempotency-Key Store
=====================

``resilience.RetryPolicy`` *re-executes* on retry and ``work_queue`` dedups only
in-flight references — nothing cached the first result so a duplicate request
returns the *same* response without re-running the side effect. This is the
Stripe idempotency pattern: register a key, run the work once, and replay the
stored response for any duplicate.

Pure standard library (``hashlib`` / ``json``); imports no ``PySide6``. The
clock is injectable and the store is in-memory with JSON persistence, so TTL
expiry and replay are fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import IdempotencyStore, request_fingerprint

    store = IdempotencyStore(ttl=86400)
    state = store.begin("order-42", request_fingerprint(payload))
    if state["status"] == "completed":
        return state["response"]            # replay — do not re-run
    result = charge(payload)                 # run the side effect once
    store.complete("order-42", result)

``begin`` returns ``{status, response}`` where status is ``new`` (first time),
``in_progress`` (a duplicate before completion), or ``completed`` (replay the
stored response); reusing a key with a different ``request`` fingerprint raises
``IdempotencyConflict`` (Stripe's HTTP-400 behaviour). ``complete`` records the
response, ``get`` reads a live record, and ``save`` / ``load`` persist the store
as JSON. ``request_fingerprint`` is a stable, order-independent SHA-256 of a
payload.

Executor commands
-----------------

``AC_idempotency_begin`` registers/looks up a ``key`` in a named store (optional
``request`` for conflict detection); ``AC_idempotency_complete`` stores the
``response``. Both use a named-instance registry (like circuit breakers /
bulkheads) and are exposed as MCP tools (``ac_idempotency_begin`` /
``ac_idempotency_complete``) and as Script Builder commands under **Flow**.
