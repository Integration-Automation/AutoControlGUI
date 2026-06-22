ORB Feature Matching (Rotation / Scale / Theme Robust)
======================================================

Pixel template matching — ``match_template``, ``match_masked`` — correlates the
template's pixels against the screen, so it breaks the moment the target is
*rotated*, scaled by a factor you did not list, or re-coloured (a light-vs-dark
theme, a hover state, a different skin). ``feature_match`` instead matches
*keypoints*: distinctive corners described by orientation-invariant binary
descriptors (ORB), then fits a RANSAC homography through the consistent ones. It
locates the element under rotation, scale and appearance change, and reports the
four projected corners plus the inlier count as a built-in confidence signal.

It runs on an injectable ``haystack`` image (ndarray / path / PIL), so it is
unit-testable on synthetic arrays without a real screen. ORB, the brute-force
matcher and ``findHomography`` are all in core OpenCV (no contrib modules);
OpenCV + NumPy come in via ``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import feature_match

    hit = feature_match("logo.png", min_inliers=12)
    if hit:
        click(*hit.center)            # centre of the located quad
        print(hit.corners)            # 4 [x, y] points, in template order
        print(hit.inliers, hit.score) # geometric inliers and inlier fraction

``feature_match`` returns a ``FeatureMatch`` (``corners``, ``center``,
``inliers``, ``matches``, ``score``) or ``None`` when fewer than ``min_inliers``
geometrically consistent matches survive. ``ratio`` is Lowe's ratio-test cutoff
(lower = stricter); ``max_features`` caps the ORB keypoint budget. The ORB border
and patch sizes are scaled down automatically for icon-sized templates, which
OpenCV's defaults would otherwise reject outright.

Executor command
----------------

``AC_feature_match`` takes ``template`` plus ``region`` / ``max_features`` /
``ratio`` / ``min_inliers`` and returns ``{found, match}``. It is exposed as the
MCP tool ``ac_feature_match`` and as a Script Builder command under **Image**.
