Multi-Template Consensus Matching
=================================

A button often renders in several states — default / hover / pressed / disabled — yet it is a
single logical target. ``ab_locator`` A/B-tests *which single strategy wins* and
``match_template(scales=...)`` sweeps *one* template across scales — neither fuses *multiple
reference crops* into one vote. ``match_ensemble`` matches each reference, clusters the hit
centres and accepts a target only when at least ``min_votes`` references agree within
``agree_px`` — sharply cutting false positives on themed / animated UI.

The voting core (``vote_centers``) is pure-stdlib and reuses ``grounding_consensus`` for the
clustering, so it is unit-testable with no image; only ``match_ensemble`` itself calls
``visual_match.match_template`` (testable on a synthetic injected ``haystack``). Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_ensemble, vote_centers

    # three reference crops of the same button (default / hover / pressed)
    result = match_ensemble(["btn_default.png", "btn_hover.png", "btn_pressed.png"],
                            min_score=0.8, agree_px=10, min_votes=2)
    if result:
        click(*result["point"])     # {point, votes, n_candidates, spread}

    # or vote hit centres you already have
    vote_centers([[100, 100], [102, 98], [400, 400]], agree_px=10, min_votes=2)

``match_ensemble`` returns ``{point, votes, n_candidates, spread}`` for the consensus location,
or ``None`` if fewer than ``min_votes`` references agree. ``vote_centers`` is the pure voting
step over candidate centres you supply.

Executor commands
-----------------

``AC_match_ensemble`` (``templates`` / ``min_score`` / ``agree_px`` / ``min_votes`` /
``region`` → ``{found, result}``) and ``AC_vote_centers`` (``centers`` / ``agree_px`` /
``min_votes`` → ``{found, result}``). They are exposed as the MCP tools ``ac_match_ensemble`` /
``ac_vote_centers`` (read-only) and as the Script Builder commands **Match Ensemble (vote
references)** / **Vote Centers (consensus)** under **Image**.
