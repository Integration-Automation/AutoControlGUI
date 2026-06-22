Model-Free Text-Region Detection (MSER)
=======================================

``shape_locator`` finds rectangular contours (buttons / cards, not text) and
``locate_text`` needs a Tesseract / Paddle engine *and* the exact string to search
for. Neither answers "where is there *any* text on screen?" without running OCR or
knowing the words. ``find_text_regions`` and ``find_text_lines`` use MSER (Maximally
Stable Extremal Regions) to find the glyph / word / line blobs, so a script can crop
the candidate text boxes to feed OCR — far faster and more accurate than full-frame
OCR — or simply detect that a label appeared with no OCR dependency installed.

Runs on an injectable ``haystack`` (ndarray / path / PIL), so it is headless-testable
on synthetic arrays. ``cv2.MSER_create`` is base OpenCV (no contrib); OpenCV + NumPy
come in via ``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import find_text_regions, find_text_lines

    # Crop each text line and OCR just that strip.
    for line in find_text_lines(y_tolerance=8):
        text = locate_text  # ... feed the cropped region to your OCR of choice
        print(line["x"], line["y"], line["width"], line["height"])

    # Or per-glyph / per-word regions.
    for box in find_text_regions(min_area=80):
        highlight(box["x"], box["y"], box["width"], box["height"])

``find_text_regions`` returns ``{x, y, width, height, area, center}`` per region,
largest first; ``merge`` unions MSER's nested per-glyph detections, ``min_area`` /
``max_area`` drop specks and page-sized blobs, ``max_aspect`` rejects long thin rules.
``find_text_lines`` groups glyph boxes whose vertical centres are within
``y_tolerance`` pixels into one box per line, top-to-bottom. A blank screen returns an
empty list (the whole-frame extremal region is filtered out).

Executor commands
-----------------

``AC_find_text_regions`` (``min_area`` / ``max_area`` / ``merge`` / ``max_aspect`` /
``region`` → ``{count, regions}``) and ``AC_find_text_lines`` (``y_tolerance`` /
``region`` → ``{count, lines}``). They are exposed as the MCP tools
``ac_find_text_regions`` / ``ac_find_text_lines`` and as Script Builder commands
under **Image**.
