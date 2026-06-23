Trust-Scored Template Matching (Ambiguity / PSR)
================================================

``match_template`` returns the single best score and happily clicks it — but a control
repeated in a toolbar, or a near-identical sibling, correlates ~0.95 in *two* places, so a
high score does **not** mean an *unambiguous* match, and the matcher can confidently click
the wrong one. ``match_with_trust`` adds a Lowe-style ratio test *for pixel templates*
(``feature_match`` already does this for ORB keypoints, but nothing did it for
``match_template``): it inspects the whole correlation surface, compares the global peak to
the next-best peak outside an exclusion window, and computes the peak-to-sidelobe ratio
(PSR), flagging matches that are strong-but-ambiguous.

It reuses ``visual_match._score_map`` — the full ``matchTemplate`` surface the public matchers
discard — so no matching code is duplicated. The ``haystack`` is injectable (ndarray / path /
PIL); the analysis is unit-testable on synthetic arrays. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_with_trust, score_peaks

    hit = match_with_trust("save_button.png", min_score=0.8)
    if hit and not hit.is_ambiguous:
        click(*hit.center)
    elif hit:
        print("ambiguous!", hit.peak_ratio, "second:", hit.second_score)

    # just the metrics, no match object
    print(score_peaks("icon.png"))   # {best, second, peak_ratio, psr, ambiguous, location}

``match_with_trust`` returns a ``TrustedMatch`` (``x`` / ``y`` / ``width`` / ``height`` /
``score`` / ``scale`` / ``second_score`` / ``peak_ratio`` / ``psr`` / ``is_ambiguous`` +
``center``) or ``None``. ``is_ambiguous`` is set when the next-best peak scores at least
``ambiguous_ratio`` (default 0.9) times the best. ``psr`` is the peak-to-sidelobe ratio
(``None`` when the sidelobe is perfectly flat). ``score_peaks`` returns just the metric dict
at scale 1.0.

Executor command
----------------

``AC_match_with_trust`` (``template`` / ``min_score`` / ``scales`` / ``ambiguous_ratio`` /
``region`` / ``method`` → ``{found, match}``) is exposed as the MCP tool
``ac_match_with_trust`` (read-only) and as the Script Builder command **Match Template
(trust-scored)** under **Image**.
