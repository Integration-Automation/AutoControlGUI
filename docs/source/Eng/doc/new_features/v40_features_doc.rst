Fuzzy String Matching & Dedupe
==============================

Exact string comparison is brittle when text comes from OCR or shifting UI copy.
These helpers score similarity, pick the best candidate from a list, and collapse
near-duplicates — so a flow can act on "the button that *looks like* Submit"
rather than an exact label.

The default backend is the standard library :mod:`difflib`, so the feature works
with **zero extra dependencies**. If the optional ``rapidfuzz`` package is
installed (``pip install je_auto_control[fuzzy]``) it is used instead for speed;
scores are normalised to ``0.0..1.0`` either way, so callers never depend on
which backend ran. ``BACKEND`` names the active one. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        fuzzy_ratio, fuzzy_best_match, fuzzy_matches, fuzzy_dedupe)

    fuzzy_ratio("Sumbit", "Submit")          # ~0.83 (case-insensitive default)

    fuzzy_best_match("Sve", ["Cancel", "Save", "Submit"])
    # -> ("Save", 0.86, 1)   (choice, score, index) — or None below score_cutoff

    fuzzy_matches("login", ["login", "logon", "logout"], limit=2)
    # -> [("login", 1.0, 0), ("logon", 0.8, 1)]  sorted best-first

    fuzzy_dedupe(["Invoice", "invoice ", "Receipt"], threshold=0.85)
    # -> ["Invoice", "Receipt"]   near-duplicates collapse, first kept

All functions take ``ignore_case`` (default ``True``); ``fuzzy_best_match`` /
``fuzzy_matches`` take ``score_cutoff`` to drop weak candidates.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_fuzzy_ratio``               ``{score}`` similarity between two strings.
``AC_fuzzy_best_match``          ``{match, score, index}`` (or null) from choices.
``AC_fuzzy_dedupe``              ``{unique}`` with near-duplicates collapsed.
================================ ===================================================

``choices`` / ``items`` accept a list or a JSON-string list (so the visual
builder works). The same operations are exposed as MCP tools (``ac_fuzzy_ratio``
/ ``ac_fuzzy_best_match`` / ``ac_fuzzy_dedupe``) and as Script Builder commands
under **Data**.
