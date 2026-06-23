Structural-Similarity (SSIM) Comparison
=======================================

The framework already compares screens by raw pixel diff (``diff_screenshots``)
and by colour histogram (``detect_drift``) — but neither is *structural*. A pixel
diff fires on a one-pixel shift or a brightness change that a human would ignore;
a histogram is blind to layout (swap two halves of the screen and it is
unchanged). SSIM is the standard visual-regression metric: tolerant of small
illumination changes, sensitive to structural change (edited text, moved or
missing elements). ``ssim_compare`` returns a single 0..1 score, and
``ssim_changed_regions`` returns the boxes of *what* actually changed.

It is a pure NumPy + OpenCV implementation (no scikit-image dependency) over an
injectable image pair, so it is unit-testable on synthetic arrays without a real
screen. OpenCV + NumPy come in via ``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import ssim_compare, ssim_changed_regions

    # Gate a visual regression test against a golden screenshot.
    score = ssim_compare("golden.png")           # current = live screen
    assert score > 0.98

    # Ignore a live clock / blinking cursor, then show what moved.
    for box in ssim_changed_regions("golden.png", ignore=[[0, 0, 120, 30]]):
        print(box["x"], box["y"], box["width"], box["height"])

``ssim_compare`` returns the mean SSIM over the image (``1.0`` = identical);
``current`` defaults to a screen grab of the optional ``region``. ``ignore`` is a
list of ``[x, y, w, h]`` boxes excluded from the score and from change detection.
``ssim_changed_regions`` flags pixels where local dissimilarity ``1 - SSIM``
exceeds ``threshold``, groups the connected ones (``min_area`` and up) and returns
``{x, y, width, height, area, center}`` largest first. Comparing two
different-sized images raises ``ValueError``.

Executor commands
-----------------

``AC_ssim_compare`` (``reference`` / ``current`` / ``ignore`` / ``region`` →
``{score}``) and ``AC_ssim_changed_regions`` (also ``threshold`` / ``min_area`` →
``{count, regions}``). They are exposed as the MCP tools ``ac_ssim_compare`` /
``ac_ssim_changed_regions`` and as Script Builder commands under **Image**.
