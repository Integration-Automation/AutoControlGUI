Colour-Aware Template Matching (HSV)
====================================

Every matcher in ``visual_match`` converts to grayscale first, so a red versus green status
indicator of identical shape is *indistinguishable* to ``match_template`` — the discriminating
signal is thrown away. ``color_region`` finds blobs of a *known* colour but cannot
template-match a multi-colour glyph by appearance. ``color_match`` matches on the HSV
hue / saturation channels using a colour-*distance* metric (``TM_SQDIFF_NORMED``, not a
correlation — correlation normalises away the absolute hue, so a red→green edge and a
black→blue edge would score the same), locating colour-discriminated targets that grayscale
matching collapses.

It reuses ``color_region``'s RGB loaders and ``visual_match``'s resize / NMS / ``Match``. The
``haystack`` is injectable; the search is unit-testable on synthetic arrays. Imports no
``PySide6``.

Note: like any window metric, a *flat* single-colour patch has no per-channel variance — for
solid colour blobs use ``find_color_region``; ``color_match`` is for targets with colour
*structure*.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_color, match_color_all

    # locate a red status chip, not the green one of the same shape
    hit = match_color("status_red.png", channels=("h", "s"), min_score=0.7)
    if hit:
        click(*hit.center)

    for m in match_color_all("tag_green.png", channels=("h",)):
        print(m.center, m.score)

``match_color`` returns the best ``Match`` over the chosen ``channels`` (default ``("h", "s")``;
use ``("h",)`` for flat-saturation targets), or ``None``. ``match_color_all`` returns every
match at or above ``min_score`` with overlaps removed by NMS.

Executor commands
-----------------

``AC_match_color`` (``template`` / ``channels`` / ``min_score`` / ``scales`` / ``region`` →
``{found, match}``) and ``AC_match_color_all`` (adds ``max_results`` / ``nms_iou`` →
``{count, matches}``). They are exposed as the MCP tools ``ac_match_color`` /
``ac_match_color_all`` (read-only) and as the Script Builder commands **Match Template
(colour/HSV)** / **Match Template All (colour/HSV)** under **Image**.
