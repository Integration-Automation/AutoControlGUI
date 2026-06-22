Statistics & A/B Significance
=============================

``ab_locator`` ranks strategies by raw success rate and ``run_history`` stores
durations, but nothing computed percentiles or told you whether a difference is
*statistically significant* rather than noise. This adds the analysis layer:
summary statistics, a two-proportion z-test, Welch's t-test, Cohen's d, and a
2x2 chi-square test.

The normal CDF is exact via ``math.erf``; the t-distribution p-value uses the
regularized incomplete beta function, so results match reference
implementations without SciPy. Pure standard library; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        describe, percentile, two_proportion_z_test, welch_t_test, cohens_d)

    describe([12.0, 9.5, 14.2, 11.1])
    # {"n": 4, "min": 9.5, "max": 14.2, "mean": 11.7, "stdev": ...,
    #  "p50": ..., "p90": ..., "p95": ..., "p99": ...}

    # Did variant B convert better than A? (90/200 vs 110/200)
    result = two_proportion_z_test(90, 200, 110, 200)
    # {"z": 2.0, "p_value": 0.0455, "significant": True,
    #  "diff": 0.1, "ci_low": ..., "ci_high": ...}

    # Continuous metric (e.g. latencies): is B different from A?
    welch_t_test(a_samples, b_samples)        # {t, df, p_value, significant, ci}
    cohens_d(a_samples, b_samples)            # effect size

``percentile`` supports linear interpolation (default) or nearest-rank;
``describe`` adds p50/p90/p95/p99 to the usual moments. ``two_proportion_z_test``
uses the pooled standard error for the test and the unpooled SE for the
confidence interval (the textbook convention). ``welch_t_test`` reports the
Welch–Satterthwaite degrees of freedom and an exact t-distribution p-value.
``chi_square_2x2`` gives the df=1 chi-square (which equals the z-test's ``z²``
for the same table). These pair naturally with ``ab_locator`` counts and
``run_history`` durations.

Executor commands
-----------------

``AC_describe_stats`` takes ``values`` (a numeric list or JSON string) and
returns the summary dict. ``AC_ab_significance`` takes ``a_conv`` / ``a_n`` /
``b_conv`` / ``b_n`` and returns the two-proportion z-test result. Both are
exposed as MCP tools (``ac_describe_stats`` / ``ac_ab_significance``) and as
Script Builder commands under **Data**.
