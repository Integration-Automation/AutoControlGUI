Rotation- and Scale-Tolerant Template Matching
==============================================

``match_template`` searches a template across *scales* (DPI / zoom tolerance) but
assumes it is axis-aligned — OpenCV's ``matchTemplate`` is not rotation-invariant,
so a control rendered at a slight skew, a rotated icon, or a dial/knob at a different
angle is missed. ``match_rotated`` adds a rotation sweep: each angle is applied to
the template with ``cv2.warpAffine``, crossed with a ``np.linspace`` scale-space, and
the best-correlating (scale, angle) is returned — so the caller also learns the
recovered *pose*.

It reuses ``visual_match``'s grayscale loaders, scale resize, correlation-method
table and non-maximum suppression, so no matching or geometry code is duplicated.
The ``haystack`` is injectable (ndarray / path / PIL), so the search is unit-testable
on synthetic arrays; only the default (grab the screen) is device-bound. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_rotated, match_rotated_all, scale_space

    # find a knob that may be turned to any of these angles, at any of these scales
    hit = match_rotated("knob.png", angles=[-15, 0, 15, 30],
                        scales=scale_space(0.9, 1.1, 3), min_score=0.85)
    if hit:
        print(hit.angle, hit.scale, hit.score, hit.center)

    # every rotated occurrence, overlaps merged by NMS
    for m in match_rotated_all("arrow.png", angles=[0, 90, 180, 270]):
        print(m.center, m.angle)

``match_rotated`` returns a single ``RotatedMatch`` (``x`` / ``y`` / ``width`` /
``height`` / ``score`` / ``scale`` / ``angle`` + ``center``) or ``None``;
``match_rotated_all`` returns every hit at or above ``min_score`` with overlapping
detections from neighbouring angles / scales collapsed by NMS, ordered by score.
``scale_space(min, max, steps)`` is a helper returning evenly spaced scales.

Executor commands
-----------------

``AC_match_rotated`` (``template`` / ``min_score`` / ``angles`` / ``scales`` /
``region`` / ``method`` → ``{found, match}``) and ``AC_match_rotated_all`` (adds
``max_results`` / ``nms_iou`` → ``{count, matches}``). They are exposed as the MCP
tools ``ac_match_rotated`` / ``ac_match_rotated_all`` (read-only) and as Script
Builder commands **Match Template (rotated)** / **Match Template All (rotated)**
under **Image**.
