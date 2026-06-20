Coordinate-Space Mapping (Model Grid ⇄ Physical Pixels)
=======================================================

Computer-use / VLA models do not click in physical pixels. Anthropic recommends
downscaling the screenshot to XGA (~1024×768) and mapping clicks back; Gemini's
computer-use model returns a normalized **1000×1000** grid; others assume the
display size you declared. ``CoordinateSpace`` captures the physical resolution
and the model's grid and converts both ways, so an agent loop can feed the model
a right-sized screenshot and translate its clicks back to real coordinates.

The mapping is pure arithmetic (no dependency); :func:`downscale_png` uses Pillow
(already a core dependency). Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        CoordinateSpace, xga_space, normalized_space, downscale_png)

    space = normalized_space(1920, 1080, grid=1000)   # Gemini-style 1000x1000
    space.to_physical(500, 500)        # -> (960, 540)   model click -> real pixel
    space.to_model(960, 540)           # -> (500, 500)   real pixel -> model grid

    xga = xga_space(2560, 1440)        # Anthropic-style downscale, aspect-preserved
    small_png = downscale_png(screenshot_png, xga)   # send this to the model

``xga_space`` preserves aspect ratio and never upscales; ``normalized_space``
builds a square grid. Both ``to_physical`` / ``to_model`` round and clamp to valid
pixel/grid bounds.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_to_physical``               Map a model-grid ``(x, y)`` to physical pixels.
``AC_to_model``                  Map physical pixels to a model grid (inverse).
================================ ===================================================

Both take ``x, y, physical_w, physical_h, model_w, model_h`` and return
``{x, y}``. The same operations are exposed as MCP tools (``ac_to_physical`` /
``ac_to_model``) and as Script Builder commands under **Agent**.
