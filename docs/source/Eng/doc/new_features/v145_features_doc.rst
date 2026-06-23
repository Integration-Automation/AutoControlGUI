Colour-Histogram Fingerprint & Change Detection
===============================================

``image_dedup`` fingerprints with a perceptual aHash / dHash — a *spatial* 64-bit
hash that is brittle to colour and theme shifts — and ``color_stats`` reports a single
average / dominant colour. A normalized colour *histogram* is the standard
illumination- and scale-robust signal for "is this the same view, or has the palette
shifted?": a theme switch, a content reload, a rotated banner — which neither hashing
nor one dominant colour captures.

Every function runs on an injectable image (ndarray / path / PIL, RGB), so it is
headless-testable on synthetic arrays. ``cv2.calcHist`` / ``cv2.compareHist`` are base
OpenCV; OpenCV + NumPy come in via ``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (image_histogram, compare_histograms,
                                 histogram_changed)

    baseline = image_histogram("golden.png")          # 3 * bins floats (HSV)
    if histogram_changed("golden.png"):               # current = live screen
        print("the view changed")

    score = compare_histograms(baseline, image_histogram())   # 1.0 == identical

``image_histogram`` returns a per-channel normalized histogram as a flat list
(``space`` = ``hsv`` / ``rgb`` / ``gray``; each channel adds ``bins`` values).
``compare_histograms`` supports ``correlation`` / ``chisqr`` / ``intersection`` /
``bhattacharyya`` (for correlation / intersection higher is more similar; for the
distance methods higher is more different). ``histogram_changed`` compares a
``reference`` against ``current`` (default: the screen) and returns a bool, flipping
the threshold comparison automatically for similarity vs distance methods.

Executor commands
-----------------

``AC_image_histogram`` (``source`` / ``bins`` / ``space`` / ``region`` →
``{bins, space, histogram}``) and ``AC_histogram_changed`` (``reference`` /
``current`` / ``method`` / ``threshold`` / ``space`` / ``region`` →
``{changed, score}``). They are exposed as the MCP tools ``ac_image_histogram`` /
``ac_histogram_changed`` and as Script Builder commands under **Image**.
