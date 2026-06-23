Locate UI Elements by Edge / Contour (No Template)
==================================================

Every locator so far needs something to look *for*: ``match_template`` and
``feature_match`` need a reference image, ``find_color_region`` needs a colour,
``locate_text`` needs the text. None of them answers the structural question
"where are the clickable boxes on this screen?". ``find_shapes`` and
``find_rectangles`` run Canny edge detection plus contour extraction and return
the bounding boxes of the distinct shapes — so a script can enumerate the cards,
buttons or input fields on a screen it has never seen and act on the Nth one,
without ever supplying a sample.

Both run on an injectable ``haystack`` image (ndarray / path / PIL), so they are
unit-testable on synthetic arrays without a real screen. OpenCV + NumPy come in
via ``je_open_cv``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import find_shapes, find_rectangles

    # Every distinct shape, largest first.
    for shape in find_shapes(min_area=500):
        print(shape["x"], shape["y"], shape["width"], shape["height"])

    # Just the wide, button-shaped rectangles, then click the first.
    buttons = find_rectangles(min_area=800, aspect_range=(1.5, 8.0))
    if buttons:
        click(*buttons[0]["center"])

``find_shapes`` returns ``{x, y, width, height, area, center, aspect}`` for every
contour (``area`` is the bounding-box area), largest first; ``min_area`` /
``max_area`` drop specks and the full-frame border. ``find_rectangles`` keeps only
contours that approximate to a convex quadrilateral (``epsilon`` is the
``approxPolyDP`` tolerance as a fraction of the perimeter) and adds an optional
``aspect_range`` ``(min, max)`` width/height filter — ``(1.5, 8)`` for wide
buttons, ``(0.8, 1.2)`` for square icons.

Executor commands
-----------------

``AC_find_shapes`` (``region`` / ``min_area`` / ``max_area`` → ``{count, shapes}``)
and ``AC_find_rectangles`` (also ``aspect_range`` / ``epsilon`` →
``{count, rectangles}``). They are exposed as the MCP tools ``ac_find_shapes`` /
``ac_find_rectangles`` and as Script Builder commands under **Image**.
