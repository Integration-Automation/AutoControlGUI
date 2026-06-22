Masked Template Matching (Ignore the Background)
================================================

Plain template matching scores *every* pixel of the template, so an icon clipped
from one background fails to match the same icon over a different one — a toolbar
glyph on a hovered vs. idle button, a cursor over arbitrary content, a logo on a
themed surface. ``match_masked`` counts only the pixels you mark as relevant: an
explicit grayscale ``mask`` (non-zero = use), or — if you pass an RGBA template —
its alpha channel. The transparent / "don't care" pixels stop dragging the score
down.

It builds on the same ``Match`` result as :doc:`v127_features_doc` (top-left,
size, ``score``, ``center``) and runs on an injectable ``haystack`` (ndarray /
path / PIL), so it is unit-testable on synthetic arrays. Matching uses OpenCV's
masked ``TM_CCORR_NORMED`` (the only normed metric that accepts a mask without
producing NaNs); non-finite cells are zeroed. OpenCV + NumPy come in via
``je_open_cv``; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_masked, match_masked_all

    # A PNG icon with transparency — its alpha is the mask automatically.
    hit = match_masked("save_icon.png", min_score=0.9)
    if hit:
        click(*hit.center)

    # An explicit mask: only the white pixels of mask.png are compared.
    for hit in match_masked_all("cursor.png", mask="cursor_mask.png",
                                min_score=0.95):
        print(hit.x, hit.y, hit.score)

``match_masked`` returns the single best ``Match`` at or above ``min_score`` (or
``None``); ``match_masked_all`` returns every match with overlaps removed by
non-maximum suppression, highest score first, capped at ``max_results``. A mask
whose shape does not match the template raises ``ValueError``.

Executor commands
-----------------

``AC_match_masked`` / ``AC_match_masked_all`` take ``template`` (and optional
``mask``) plus ``min_score`` / ``region`` (and ``max_results`` / ``nms_iou`` for
the *all* form). They are exposed as the MCP tools ``ac_match_masked`` /
``ac_match_masked_all`` and as Script Builder commands under **Image**.
