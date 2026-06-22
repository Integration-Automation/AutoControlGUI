Streaming Latency Percentiles
=============================

``stats.percentile`` is exact but needs the full sorted sample list in memory;
for a long-running or sharded load / soak run you want an O(1)-per-record,
bounded-memory, *mergeable* structure instead. This adds a HdrHistogram-style
:class:`LatencyDigest` (records into significant-figure buckets, merges across
shards) plus :func:`exact_percentiles` for small sample sets.

Pure standard library (``math``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import LatencyDigest, exact_percentiles

    digest = LatencyDigest(sig_figs=3)
    for latency_ms in stream:
        digest.record(latency_ms)        # O(1), bounded memory
    print(digest.summary())              # min/mean/max/p50/p90/p95/p99

    # merge per-shard digests into one
    total = shard_a.merge(shard_b)

    # exact percentiles for a small in-memory set
    exact_percentiles([12.0, 9.5, 14.2], qs=(50, 95))

``LatencyDigest.record`` buckets each value to ``sig_figs`` significant figures
(so memory is bounded by the number of distinct rounded values, not the sample
count); ``percentile`` / ``quantiles`` / ``summary`` read it back, and ``merge``
folds another digest in for cross-shard aggregation — the property you need to
compute a correct aggregate p99 from per-worker results. ``exact_percentiles``
delegates to ``stats.percentile`` for the small-set case.

Executor command
----------------

``AC_percentiles`` takes ``samples`` (a list or JSON string) and optional ``qs``
quantiles (default 50/90/95/99) and returns ``{percentiles}``. The same
operation is exposed as the MCP tool ``ac_percentiles`` and as a Script Builder
command under **Report**.
