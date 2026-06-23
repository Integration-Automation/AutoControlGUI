Sub-Pixel Template-Match Refinement
===================================

Every matcher (``match_template`` / ``match_rotated`` / ``match_masked``) returns *integer*
pixel coordinates straight from ``cv2.minMaxLoc``. For a drag handle, a fine slider, a
sub-pixel-rendered target, or a high-DPI display, that integer rounding is the dominant
click-placement error. ``subpixel_match`` refines the peak to a fraction of a pixel by fitting
a parabola to the 3x3 score neighbourhood around the integer maximum — independently on x and y
(the standard NCC sub-pixel method).

It reuses ``visual_match._score_map`` (the full ``matchTemplate`` surface the public matchers
discard); no matching code is duplicated. The ``haystack`` is injectable; the analysis is
unit-testable on synthetic arrays. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_subpixel, refine_peak

    hit = match_subpixel("slider_thumb.png", min_score=0.8)
    if hit:
        # cx / cy are floats — pass to a sub-pixel-aware drag / move
        move_to(hit.cx, hit.cy)

    # the fitting primitive over any score surface
    offset_x, offset_y = refine_peak(score_map, (peak_x, peak_y))

``match_subpixel`` returns a ``SubPixelMatch`` (integer ``x`` / ``y`` / ``width`` / ``height`` /
``score`` plus float ``cx`` / ``cy`` and the ``offset_x`` / ``offset_y`` applied), or ``None``
below ``min_score``. ``refine_peak`` returns the ``[-0.5, 0.5]`` quadratic-fit offset of a peak
from its neighbours — usable on any correlation surface.

Executor command
----------------

``AC_match_subpixel`` (``template`` / ``min_score`` / ``region`` / ``method`` →
``{found, match}``) is exposed as the MCP tool ``ac_match_subpixel`` (read-only) and as the
Script Builder command **Match Template (sub-pixel)** under **Image**.
