==================================================
New Features (2026-06-19) — Resilience Primitives
==================================================

Reusable resilience primitives — a retry-with-backoff policy and a circuit
breaker — plus an executor command that runs an action list through a named
breaker. Pure standard library; both primitives take injectable
``sleep`` / ``clock`` so they are unit-tested deterministically.

(The existing ``AC_retry`` flow command already retries an action *body*;
this adds the reusable :class:`RetryPolicy` callable wrapper and the new
:class:`CircuitBreaker`.)

.. contents::
   :local:
   :depth: 2


RetryPolicy
==========

::

    from je_auto_control import RetryPolicy, retry_call

    RetryPolicy(max_attempts=5, backoff=0.1, multiplier=2.0).run(flaky_fn)
    retry_call(flaky_fn, max_attempts=3)     # convenience

Retries ``func`` on the configured ``exceptions`` with exponential backoff
(``backoff * multiplier**n``, optionally capped by ``max_backoff``),
re-raising the last error when attempts are exhausted.


CircuitBreaker
=============

::

    from je_auto_control import CircuitBreaker, CircuitOpenError

    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30.0)
    try:
        breaker.call(call_remote_service)
    except CircuitOpenError:
        ...   # short-circuited — the dependency is down

Opens after ``failure_threshold`` consecutive failures and short-circuits
(raising :class:`CircuitOpenError`) until ``reset_timeout`` elapses, then
half-opens for one trial; a success closes it. Stops a retry storm from
hammering a downed dependency.

``AC_circuit_call`` / ``ac_circuit_call`` run an action list through a
**named** breaker (state shared across calls), returning ``{state, record}``.
