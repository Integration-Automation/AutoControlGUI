Theme-Invariant Matching (Light Template, Dark Mode)
====================================================

``match_template`` correlates raw pixel intensities, so a template captured in
light mode scores terribly against the same control in dark mode — the polarity
is inverted. The fix is to compare *structure* (edges, gradients), which is the
same regardless of which way the colours run. ``theme_normalize`` turns an image
into a polarity-invariant representation before matching.

* :func:`normalize_theme` — map an image to a normalised single-channel image.
  ``sobel`` (default) and ``laplacian`` use gradient magnitude, which is
  identical for an image and its colour-inverse; ``zscore`` standardises
  intensity.
* :func:`match_theme` — :func:`normalize_theme` both the template and the
  haystack (the screen by default), then locate the template — finding it across
  a light/dark theme flip that defeats raw matching.

``cv2`` / ``numpy`` are imported lazily, so importing the module never requires
them, and the locating logic reuses :func:`visual_match.match_template`. Imports
no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_theme, normalize_theme

    # A button template grabbed in light mode, found in the dark-mode app:
    hit = match_theme("save_button_light.png", method="sobel", min_score=0.4)
    if hit and hit["score"] >= 0.5:
        click(hit["x"] + hit["width"] // 2, hit["y"] + hit["height"] // 2)

    # The transform itself (e.g. to feed your own matcher):
    edges = normalize_theme("template.png", method="sobel")

Because gradient magnitude is identical for an image and its inverse,
``normalize_theme(img, "sobel")`` equals ``normalize_theme(255 - img, "sobel")``
— that invariance is exactly what lets one template match both themes. Use
``min_score`` lower than for raw matching (structure correlation runs cooler).

Executor commands
-----------------

``AC_match_theme`` (``template`` + ``region`` ``[x, y, w, h]`` / ``method`` /
``min_score`` → ``{found, x, y, width, height, score}``) locates a template
across a theme flip. It is the matching read-only ``ac_match_theme`` MCP tool and
a Script Builder command under **Image**. :func:`normalize_theme` (which returns
an image array) is the Python-API surface.
