=================
Screen Operations
=================

AutoControl provides functions for capturing screenshots and retrieving screen dimensions.

Screenshot
==========

Capture the current screen and save to a file:

.. code-block:: python

   from je_auto_control import screenshot

   # Save a full-screen screenshot
   screenshot("my_screenshot.png")

   # Capture a specific region [x1, y1, x2, y2]
   screenshot("region.png", screen_region=[100, 100, 500, 400])

``screen_region`` is in the coordinates the mouse takes. On Windows it may lie
on any monitor — a monitor left of or above the primary one has negative
coordinates, e.g. ``screen_region=[-1920, 0, -1720, 100]`` — and the image is
always ``x2 - x1`` by ``y2 - y1``: whatever part of the region is off the
desktop is black, and a region with none of it on a monitor raises
``AutoControlScreenException``. Without ``screen_region`` the primary monitor
is captured.

Coordinates and DPI on Windows
------------------------------

``import je_auto_control`` makes the process **per-monitor DPI aware (v2)**,
falling back to system awareness on a Windows too old for it or in a process
whose awareness was already fixed (an embedding host, a manifest). Per-monitor
means every monitor is addressed in its own physical pixels: a 1920x1080
monitor is 1920 wide to the mouse, to ``screenshot`` and to the window
functions whatever its scale setting, and its capture is not resized.

Before this the process was *system* aware, and a monitor whose scale differs
from the primary monitor's was virtualised by Windows: it appeared
``primary scale / its scale`` times its real size (1536x864 for a 1920x1080
monitor at 125% beside a 100% primary) and its capture was a blurred, resized
image. Coordinates recorded on such a monitor, and template images cut from
it, were taken in that virtualised space and have to be recorded again; a
point at offset ``(dx, dy)`` from that monitor's top-left corner is now at
``(dx, dy) * its scale / primary scale``. The primary monitor, and any monitor
at the primary's scale, are unchanged.

Screen Size
===========

Get the current screen resolution:

.. code-block:: python

   from je_auto_control import screen_size

   width, height = screen_size()
   print(f"Screen resolution: {width} x {height}")

Get Pixel Color
===============

Retrieve the color of a pixel at specific coordinates:

.. code-block:: python

   from je_auto_control import get_pixel

   color = get_pixel(500, 300)
   print(f"Pixel color at (500, 300): {color}")
