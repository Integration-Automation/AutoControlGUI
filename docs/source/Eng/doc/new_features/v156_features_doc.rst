Weighted Candidate Scoring
==========================

``anchor_locator`` filters by a single spatial relation and sorts by distance, and
``ab_locator`` races *whole strategies* and picks by elapsed time — neither is a
*weighted multi-signal scorer* that ranks ambiguous candidates by combining a role
match, a fuzzy name similarity, proximity to an anchor and enabled state into one
confidence. That is exactly what self-healing / grounding needs when several boxes
could be the target. The name similarity is injectable (defaulting to the project's
``fuzzy_ratio``), so no new string-distance code is added.

Pure-stdlib over plain element dicts (``role`` / ``name`` / ``x`` / ``y`` / ``width`` /
``height`` / optional ``enabled``), fully unit-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import score_candidates, best_candidate

    ranked = score_candidates(candidates, want_role="button", want_name="Save",
                              anchor=(960, 540))
    for c in ranked:
        print(round(c.score, 3), c.element["name"], c.matched_on)

    pick = best_candidate(candidates, want_role="button", want_name="Save")
    if pick:
        click(*[pick.element["x"], pick.element["y"]])

``score_candidates`` returns a list of ``ScoredCandidate`` (``element`` / ``score`` /
``matched_on`` breakdown), best-first; each active signal contributes 0..1 and the
score is their mean. ``want_role`` scores 1 on an exact role match, ``want_name`` runs
``name_similarity`` (default ``fuzzy_ratio``), ``anchor`` adds a proximity term, and
``prefer_enabled`` rewards enabled elements. ``best_candidate`` returns the top one (or
``None``).

Executor commands
-----------------

``AC_score_candidates`` (``candidates`` / ``want_role`` / ``want_name`` / ``anchor`` →
``{count, scored}``) and ``AC_best_candidate`` (same inputs → ``{found, best}``). They
are exposed as the MCP tools ``ac_score_candidates`` / ``ac_best_candidate`` and as
Script Builder commands under **Native UI**.
