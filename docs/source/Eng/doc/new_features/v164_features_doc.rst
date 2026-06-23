Auto-Thresholded Template Matching (Otsu on the Score Map)
==========================================================

Every call to ``match_template_all`` forces the caller to guess ``min_score``: too low
floods NMS with background noise, too high drops scaled / re-themed targets, and the right
value differs per asset and per screen. ``match_autothresh`` removes the magic number — it
runs Otsu's method on the *correlation score histogram* (not pixel intensities, the way
``preprocess.binarize`` does) to find the valley between the "background correlation" mass
and the "real match" mass, and returns that cut-off plus a *separability* number so the
caller knows when the histogram is unimodal (no clear match → don't trust the threshold).

It reuses ``visual_match._score_map`` (the full ``matchTemplate`` surface the public matchers
discard) and ``cv2_utils.blobs.connected_boxes`` — each above-threshold region yields a single
peak, avoiding the duplicate hits a raw pixel scan + NMS leaves on a wide correlation peak. The
``haystack`` is injectable; the analysis is unit-testable on synthetic arrays. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_auto, auto_threshold

    # no min_score to tune — the threshold is derived from the score map
    for hit in match_auto("save_button.png", floor=0.5):
        print(hit.center, hit.score)

    info = auto_threshold("save_button.png")
    # {"threshold": 0.83, "separability": 0.61, "n_above": 2}
    if info["separability"] < 0.3:
        print("no clear match — threshold not trustworthy")

``match_auto`` returns one ``Match`` per above-threshold region, ordered by score and capped at
``max_results``; the cut-off is ``max(floor, otsu_threshold)`` so a unimodal / noisy surface
cannot drag it below a sane floor. ``auto_threshold`` returns ``{threshold, separability,
n_above}`` — ``separability`` near 0 means the score histogram is unimodal and the threshold
should be treated as unreliable.

Executor commands
-----------------

``AC_match_auto`` (``template`` / ``floor`` / ``max_results`` / ``region`` / ``method`` →
``{count, matches}``) and ``AC_auto_threshold`` (``template`` / ``region`` / ``method`` →
``{found, info}``). They are exposed as the MCP tools ``ac_match_auto`` / ``ac_auto_threshold``
(read-only) and as the Script Builder commands **Match Template (auto-threshold)** / **Auto
Threshold (Otsu on scores)** under **Image**.
