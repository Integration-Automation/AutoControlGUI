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
