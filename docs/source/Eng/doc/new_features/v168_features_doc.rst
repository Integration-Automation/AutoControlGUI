Edge-Shape (Chamfer) Template Matching
======================================

Intensity correlation (``visual_match``) is dragged down when the same control is rendered
with a different fill, gradient, theme or anti-aliasing, and ORB feature matching
(``feature_match``) needs corner texture that flat-design glyphs — a hamburger menu, a plain
chevron — simply do not have. ``edge_match`` locates a template by its *edge shape* instead:
it runs Canny on both images, builds a distance transform of the scene edges, and slides the
template's edges over it, scoring each position by the mean distance from a template edge to
the nearest scene edge (Chamfer matching). A perfect alignment costs ~0 regardless of how the
shape is filled or shaded.

It reuses ``visual_match``'s gray loaders / resize / NMS / ``Match`` and ``edge_lines``'s Canny
default, so no matching or geometry code is duplicated. The ``haystack`` is injectable
(ndarray / path / PIL); the search is unit-testable on synthetic arrays. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import edge_match, edge_match_all, chamfer_distance

    # find a flat icon regardless of its fill colour / theme
    hit = edge_match("chevron.png", min_score=0.7)
    if hit:
        click(*hit.center)

    for m in edge_match_all("divider_handle.png", min_score=0.8):
        print(m.center, m.score)

    print(chamfer_distance("logo_outline.png"))   # 0 = edges coincide

``edge_match`` returns the best ``Match`` (score = ``1 / (1 + mean edge distance)``, so 1.0 is
a perfect outline match) over the requested ``scales``, or ``None``. ``edge_match_all`` returns
every match at or above ``min_score`` with overlaps removed by NMS. ``chamfer_distance`` returns
the mean edge-to-edge distance at the best alignment (0 = the outlines coincide).

Executor commands
-----------------

``AC_edge_match`` (``template`` / ``min_score`` / ``scales`` / ``region`` →
``{found, match}``) and ``AC_edge_match_all`` (adds ``max_results`` / ``nms_iou`` →
``{count, matches}``). They are exposed as the MCP tools ``ac_edge_match`` /
``ac_edge_match_all`` (read-only) and as the Script Builder commands **Match Template (edge
shape)** / **Match Template All (edge shape)** under **Image**.
