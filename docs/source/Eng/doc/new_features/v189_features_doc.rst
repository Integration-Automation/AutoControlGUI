Display-Scale / Visual-DPI Detection
====================================

A template cropped at 100% display scale will not match pixel-for-pixel on a
machine running at 150% DPI — everything is 1.5x bigger. ``visual_match.
match_template`` *can* sweep scales, but it returns only the single best match's
location and throws the per-scale scores away. ``scale_detect`` keeps the whole
profile: it scores the template against the haystack at a range of scales and
reports **which scale wins, by how much**, so an automation can infer the
effective UI scale / DPI and how confident that inference is.

* :func:`scale_sweep` — the per-scale score profile (every scale's best match),
* :func:`detect_scale` — the winning scale as a DPI inference with a confidence
  margin.

It reuses ``visual_match._score_map`` (the full ``matchTemplate`` surface,
oriented higher = better) for each scale, so the source is any ndarray / path /
PIL image (or the live screen). cv2 / numpy are lazily imported. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import detect_scale, scale_sweep

    detect_scale("button.png", "screen.png")
    # {"scale": 1.5, "scale_percent": 150, "score": 0.98, "center": [...],
    #  "margin": 0.62, "candidates": [...]}

    scale_sweep("button.png", scales=[1.0, 1.25, 1.5, 1.75, 2.0])
    # [{"scale": 1.0, "score": .., "center": [..]}, {"scale": 1.25, ...}, ...]

``scales`` defaults to the common Windows display scales
``(1.0, 1.25, 1.5, 1.75, 2.0)``. ``margin`` is how far the winning scale beats the
runner-up — a low margin means the inference is ambiguous. Scales at which the
template is larger than the haystack are skipped; ``detect_scale`` returns
``None`` when none fit. Omit ``haystack`` to match against the live screen
(``region`` applies to that grab).

Executor commands
-----------------

``AC_detect_scale`` and ``AC_scale_sweep`` (``template`` / ``haystack`` /
``region`` / ``scales`` / ``method``). They are exposed as read-only ``ac_*`` MCP
tools and as Script Builder commands under **Image**.
