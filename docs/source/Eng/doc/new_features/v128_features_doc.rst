Locate On-Screen Regions by Colour
==================================

``color_stats`` only *describes* a region's dominant / average colour and
``assert_pixel`` checks a single point with a tolerance — neither *locates* a
coloured region. Template matching is brittle when only the colour is the signal
(a status light, a progress-bar fill, a red error banner). This masks pixels
within a tolerance of a target RGB and returns the bounding boxes of the
connected blobs.

The masking + connected-components run on an injectable ``haystack`` image
(ndarray / path / PIL), so it is unit-testable on synthetic arrays without a real
screen. OpenCV + NumPy come in via the project's ``je_open_cv`` dependency.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import find_color_region, find_color_regions

    pill = find_color_region([0, 200, 0], tolerance=25)      # the green status pill
    if pill:
        click(*pill["center"])

    for banner in find_color_regions([200, 0, 0], min_area=500):
        print(banner["x"], banner["y"], banner["area"])      # every red blob

``find_color_regions`` returns ``{x, y, width, height, area, center}`` for each
blob within ``tolerance`` (per channel) of ``rgb`` and at least ``min_area``
pixels, largest first; ``find_color_region`` returns just the largest (or
``None``). ``haystack`` defaults to a screen grab of the optional ``region``.

Executor commands
-----------------

``AC_find_color_region`` takes ``rgb`` (a JSON ``[r, g, b]`` array) plus
``tolerance`` / ``min_area`` / ``region`` and returns ``{count, regions, best}``.
It is exposed as the MCP tool ``ac_find_color_region`` and as a Script Builder
command under **Image**.
