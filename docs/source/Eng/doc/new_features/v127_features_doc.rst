Confidence-Returning Template Matching
======================================

The project's template matcher (``je_open_cv.find_object`` via ``cv2_utils``) is
single-scale and returns only bounding boxes — the correlation *score* it
computes internally is discarded. So there was no way to rank candidates, set a
confidence threshold and read back *how well* it matched, find a control when the
UI is DPI / zoom-scaled, or enumerate *every* occurrence. This adds those, like
PyAutoGUI ``confidence`` / ``locateAll`` and SikuliX ``similarity`` / ``findAll``.

The matching takes an injectable ``haystack`` image (ndarray / path / PIL), so it
is unit-testable on synthetic arrays without a real screen — only the default
(grab the screen) is device-bound. OpenCV + NumPy come in via the project's
``je_open_cv`` dependency. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_template, match_template_all, best_matches

    m = match_template("button.png", min_score=0.85, scales=(0.9, 1.0, 1.1))
    if m:
        print(m.score, m.scale, m.center)     # confidence + DPI scale + click point

    for hit in match_template_all("row_handle.png", min_score=0.8):
        click(*hit.center)                     # every occurrence, overlaps removed

``match_template`` returns the single best :class:`Match` (``x`` / ``y`` /
``width`` / ``height`` / ``score`` / ``scale`` / ``center``) at or above
``min_score``, searching each entry in ``scales`` for DPI / zoom tolerance.
``match_template_all`` returns every hit, merging overlapping detections by
non-maximum suppression (``nms_iou``) and capping at ``max_results``.
``best_matches`` returns the top-N by score regardless of threshold (for tuning).

Executor commands
-----------------

``AC_match_template`` returns ``{found, match}`` (the match dict carries the
score); ``AC_match_template_all`` returns ``{count, matches}``. Both are exposed
as MCP tools (``ac_match_template`` / ``ac_match_template_all``) and as Script
Builder commands under **Image**.
