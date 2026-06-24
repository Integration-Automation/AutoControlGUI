Flaky-Test Co-Failure Clustering
================================

Flaky tests are rarely independent: a wobbly shared fixture, a slow dependency or
a noisy environment makes a *group* of tests fail in the same runs (research finds
~75% of flaky tests fall into co-failure clusters). Ranking tests one-by-one by
flip rate misses that shared root cause. ``flake_cluster`` measures how often each
pair of tests fails in the *same* runs — Jaccard similarity over the set of runs
each failed in — and groups tests whose co-failure exceeds a threshold, so you can
chase one root cause instead of N symptoms.

* :func:`cofailure_pairs` — test pairs that fail together above a threshold,
* :func:`failure_clusters` — connected clusters of co-failing tests with a
  cohesion score (mean pairwise Jaccard).

Input is a list of runs, each a collection of the test names that failed in that
run. Pure standard library; no device, no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import failure_clusters, cofailure_pairs

    runs = [["test_a", "test_b"],            # both failed in this run
            ["test_a", "test_b"],
            ["test_c"],
            ["test_a", "test_b", "test_c"]]

    failure_clusters(runs, threshold=0.6)
    # [{"tests": ["test_a", "test_b"], "size": 2, "cohesion": 1.0}]

    cofailure_pairs(runs, threshold=0.6)
    # [{"tests": ["test_a", "test_b"], "jaccard": 1.0, "co_failures": 3}]

``threshold`` is the minimum co-failure Jaccard to link two tests; ``min_size``
(default ``2``) drops singletons so only genuine clusters surface. Clusters come
back largest / most cohesive first.

Executor commands
-----------------

``AC_failure_clusters`` (``runs`` / ``threshold`` / ``min_size``) and
``AC_cofailure_pairs`` (``runs`` / ``threshold``). They are exposed as read-only
``ac_*`` MCP tools and as Script Builder commands under **Testing**.
