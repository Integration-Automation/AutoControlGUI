Image Quality Scoring (sharpness / contrast / brightness gate)
==============================================================

OCR and template matching quietly fail on a blurry, washed-out or too-dark
capture — the locate returns nothing and the caller can't tell a *missing*
element from an *unreadable* one. ``image_quality`` measures the three things
that wreck recognition and gates on them:

* **sharpness** — variance of the Laplacian (low = blurry / out of focus),
* **contrast** — standard deviation of the grayscale (low = washed out),
* **brightness** — mean grayscale 0–255 (too low = dark, too high = blown out).

:func:`image_quality` returns the raw metrics, :func:`is_blurry` is the common
one-liner, and :func:`quality_gate` turns the metrics into a pass / fail verdict
with named issues, so a script can refuse to OCR a bad frame (or pre-process it
first). It reuses ``visual_match``'s grayscale loader, so the source is any
ndarray / path / PIL image (or the live screen when omitted); cv2 / numpy are
lazily imported. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import image_quality, is_blurry, quality_gate

    image_quality("frame.png")
    # {"sharpness": 842.1, "contrast": 58.3, "brightness": 131.0}

    if is_blurry("frame.png", threshold=100):
        ...  # capture again / sharpen before OCR

    gate = quality_gate("frame.png", min_sharpness=100, min_contrast=12)
    # {"sharpness": .., "contrast": .., "brightness": .., "passed": False,
    #  "issues": ["blurry", "too_dark"]}

``quality_gate`` flags ``blurry`` / ``low_contrast`` / ``too_dark`` /
``too_bright``; ``passed`` is True only when no issue fires. ``region`` applies to
a live-screen grab (omit ``source`` to grade the screen). Thresholds are tunable;
the defaults suit typical UI screenshots.

Executor commands
-----------------

``AC_image_quality`` (``source`` / ``region``) and ``AC_quality_gate`` (plus
``min_sharpness`` / ``min_contrast``). They are exposed as read-only ``ac_*`` MCP
tools and as Script Builder commands under **Image**.
