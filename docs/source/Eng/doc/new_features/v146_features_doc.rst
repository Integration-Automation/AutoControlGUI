Localized Motion / Activity Detection
=====================================

Three near-neighbours, all distinct: ``wait_until_screen_stable`` returns a *boolean*
over a live poll loop (not localized boxes on an injectable pair); ``ssim_changed_regions``
is *structural* (Gaussian-windowed SSIM, illumination-tolerant — it deliberately ignores
the fast pixel motion you want for "where is the spinner / video / animation");
``diff_screenshots`` highlights pixel diffs but is not framed as activity blobs with a
score. ``changed_regions`` / ``has_motion`` / ``activity_score`` are the cheap absdiff
path: which sub-regions are *moving* between two frames, so a script can pick a quiet
area or locate a busy spinner.

They operate on two injectable frames (ndarray / path / PIL), so they are headless-
testable on synthetic arrays, and reuse the shared connected-component helper. OpenCV +
NumPy come in via ``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import changed_regions, has_motion, activity_score

    before = screenshot_to_array()
    # ... time passes ...
    for box in changed_regions(before, after):     # boxes that moved, largest first
        print(box["x"], box["y"], box["width"], box["height"])

    if has_motion(before, after):
        print("still animating, activity =", activity_score(before, after))

``changed_regions`` thresholds the absolute difference (``threshold``), denoises
(``blur``), dilates and returns ``{x, y, width, height, area, center}`` blobs of at
least ``min_area``, largest first. ``has_motion`` is the boolean form; ``activity_score``
is the fraction (0..1) of pixels that moved. Frames of different sizes raise
``ValueError``.

Executor commands
-----------------

``AC_changed_regions`` (``before`` / ``after`` / ``threshold`` / ``min_area`` /
``blur`` → ``{count, regions}``) and ``AC_has_motion`` (``before`` / ``after`` /
``threshold`` / ``min_area`` → ``{moved, activity}``); ``after`` defaults to a live
screen grab. They are exposed as the MCP tools ``ac_changed_regions`` /
``ac_has_motion`` and as Script Builder commands under **Image**.
