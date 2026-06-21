Distribution Drift Detection
============================

``stats`` has two-sample tests for A/B *experiment* outcomes (proportions and
means), but no Population Stability Index and no Kolmogorov-Smirnov two-sample
test for the canonical "is today's data shaped like the baseline" check. This
adds PSI, KS, and a categorical-drift summary that pair with ``data_profile``.

Pure standard library (``math`` / ``bisect`` / ``collections`` + reuse of
``stats.percentile``); imports no ``PySide6``. Every function is pure
(sequences in, dict/float out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import psi, ks_two_sample, categorical_drift, detect_drift

    score = psi(reference, current)               # Population Stability Index
    ks = ks_two_sample(reference, current)        # {statistic, p_value}
    report = detect_drift(reference, current)     # {psi, drifted, ks}

    cat = categorical_drift(ref_labels, cur_labels)
    # {chi_square, total_variation, categories}

``psi`` bins ``current`` against ``reference`` quantile edges and sums the
log-ratio contribution per bin (0 for identical distributions, growing as they
diverge). ``ks_two_sample`` returns the maximum empirical-CDF gap and a p-value
from the Kolmogorov distribution. ``categorical_drift`` compares label
frequencies via a chi-square statistic and the total-variation distance.
``detect_drift`` wraps the numeric path into one report with a ``drifted``
verdict at ``threshold`` (default ``0.25``).

Executor commands
-----------------

``AC_detect_drift`` takes ``reference`` / ``current`` numeric lists (and
optional ``threshold`` / ``bins``) and returns ``{psi, drifted, ks}``.
``AC_categorical_drift`` returns the categorical summary. Both are exposed as
MCP tools (``ac_detect_drift`` / ``ac_categorical_drift``) and as Script Builder
commands under **Data**.
