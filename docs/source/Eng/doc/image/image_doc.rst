=================
Image Recognition
=================

AutoControl uses OpenCV template matching to locate UI elements on the screen.
This is useful for finding buttons, icons, or other visual elements and interacting with them.

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
