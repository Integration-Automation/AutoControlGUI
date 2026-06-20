Client-Side Rate Limiting
=========================

The framework had ``RetryPolicy`` / ``CircuitBreaker`` (which *recover* from
failures) and a FIFO ``work_queue``, but nothing to shape the *rate* of calls —
so a flow hammering an external API had no way to stay under a quota. This adds
the two standard limiters plus a leading-edge throttle, all with an injectable
clock so they are deterministic in tests (no real sleeping).

* :class:`TokenBucket` — a smooth rate with burst capacity (lazy refill).
* :class:`SlidingWindowLimiter` — a fixed call budget per rolling window
  (Cloudflare's O(1) weighted-counter approximation).
* :func:`throttle` — a decorator that fires a function at most once per interval.

Pure standard library (``threading`` for the lock, ``time`` only as the default
clock); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import TokenBucket, SlidingWindowLimiter, throttle

    # 5 requests/second, bursts up to 10
    bucket = TokenBucket(rate=5, capacity=10)
    if bucket.try_acquire():
        call_api()                      # non-blocking: skip / queue if False
    bucket.acquire()                    # or block until a token frees up

    # at most 100 calls per 60s rolling window
    window = SlidingWindowLimiter(limit=100, window_s=60)
    if window.try_acquire():
        call_api()

    @throttle(2.0)                      # fire at most once every 2 seconds
    def on_event(payload):
        ...

``TokenBucket.try_acquire`` takes tokens if available; ``acquire`` blocks (with
an optional ``timeout``); ``time_until_available`` reports the wait so a
scheduler can pace itself. Every limiter accepts a ``clock=`` (and ``acquire``
a ``sleep=``) so the whole thing is exercised in CI with a fake clock — no real
delays.

Executor command
----------------

``AC_rate_limit`` takes a limiter ``name`` plus ``rate`` / ``capacity`` / ``n``
and tries to take ``n`` tokens from that named token bucket (created on first
use), returning ``{acquired, tokens, wait}`` so a flow can gate or defer an
action. The same operation is exposed as the MCP tool ``ac_rate_limit`` and as a
Script Builder command under **Flow**.
