HSV Colour-Space Segmentation
=============================

``find_color_region`` masks in RGB with a per-channel ± tolerance box, which fails
the canonical case: a status light, highlight or theme tint that is "the same colour"
but at a different *brightness*. HSV separates hue from saturation/value, so a hue
band with a saturation/value floor catches every shade of a colour across lighting.
This adds HSV masking and blob boxes, reusing the shared connected-component helper,
with correct hue-wrap handling for red (which straddles the 0/180 boundary).

Runs on an injectable ``haystack`` (ndarray / path / PIL, RGB), so it is headless-
testable on synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import dominant_hue_regions, segment_hsv, color_mask

    # Every red region — bright or dark — regardless of lighting (red wrap handled).
    for r in dominant_hue_regions(hue=0, hue_tol=10, sat_min=80, val_min=80):
        click(*r["center"])

    # Or an explicit HSV band (H 0-179, S/V 0-255).
    greens = segment_hsv(lower_hsv=[40, 80, 80], upper_hsv=[80, 255, 255])
    mask = color_mask(lower_hsv=[40, 80, 80], upper_hsv=[80, 255, 255])

``dominant_hue_regions`` constrains only the hue (± ``hue_tol``) plus a ``sat_min`` /
``val_min`` floor to skip greys, returning ``{x, y, width, height, area, center}`` per
blob largest first — so it finds a colour at any brightness, unlike the RGB box.
``segment_hsv`` takes an explicit ``lower_hsv`` / ``upper_hsv`` band; ``color_mask``
returns the raw uint8 mask.

Executor commands
-----------------

``AC_segment_hsv`` (``lower_hsv`` / ``upper_hsv`` / ``min_area`` / ``region``) and
``AC_dominant_hue_regions`` (``hue`` / ``hue_tol`` / ``sat_min`` / ``val_min`` /
``min_area`` / ``region``), both returning ``{count, regions, best}``. They are
exposed as the MCP tools ``ac_segment_hsv`` / ``ac_dominant_hue_regions`` and as
Script Builder commands under **Image**.
