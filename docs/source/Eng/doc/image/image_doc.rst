=================
Image Recognition
=================

AutoControl prefers OpenCV template matching to locate UI elements on the screen.
This is useful for finding buttons, icons, or other visual elements and interacting with them.

Without OpenCV, a NumPy/Pillow backend provides normalized grayscale template
matching, BGR screenshot arrays, image file I/O, previews and fixed-frame healing.
Windows arm64 installs NumPy 2.4.6 on Python 3.11+. Existing Python, ``AC_*``,
GUI and MCP calls use the same backend selection. Frames are limited to
16,777,216 pixels and each tiled FFT to 4,194,304 cells. Inputs support uint8
or float32 arrays and 8-bit image files; unsupported operations or budgets
raise typed framework errors. Advanced OpenCV processing and video remain
dependent on OpenCV. Cryptography's safety floor is unchanged.

Locate All Matches
==================

Find all occurrences of a template image on the screen:

.. code-block:: python

   import time
   from je_auto_control import locate_all_image, screenshot

   time.sleep(2)

   # detect_threshold: 0.0 ~ 1.0 (1.0 = exact match)
   image_data = locate_all_image(
       screenshot(),
       detect_threshold=0.9,
       draw_image=False
   )
   print(image_data)  # [[x1, y1, x2, y2], ...]

Locate Image Center
===================

Find a template image and return its center coordinates:

.. code-block:: python

   import time
   from je_auto_control import locate_image_center, screenshot

   time.sleep(2)

   cx, cy = locate_image_center(
       screenshot(),
       detect_threshold=0.9,
       draw_image=False
   )
   print(f"Found at center: ({cx}, {cy})")

Locate and Click
================

Find a template image and automatically click on its center:

.. code-block:: python

   import time
   from je_auto_control import locate_and_click, screenshot

   time.sleep(2)

   image_data = locate_and_click(
       screenshot(),
       "mouse_left",
       detect_threshold=0.9,
       draw_image=False
   )
   print(image_data)

Parameters
==========

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Type
     - Description
   * - ``image``
     - str / PIL Image
     - The template image to search for (file path or PIL ``ImageGrab.grab()`` result)
   * - ``detect_threshold``
     - float
     - Detection precision from ``0.0`` to ``1.0``. ``1.0`` requires an exact match.
   * - ``draw_image``
     - bool
     - If ``True``, marks the detected area on the returned image.
