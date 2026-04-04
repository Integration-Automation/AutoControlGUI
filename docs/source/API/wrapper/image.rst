=========
Image API
=========

.. module:: je_auto_control

Functions for image recognition using OpenCV template matching.

----

locate_all_image
================

.. function:: locate_all_image(image, detect_threshold=1, draw_image=False)

   Locates all occurrences of a template image on the screen.

   :param image: Template image to search for (file path or PIL image).
   :type image: str or PIL.Image
   :param float detect_threshold: Detection precision from ``0.0`` to ``1.0``.
      ``1.0`` requires an exact match.
   :param bool draw_image: If ``True``, marks detected areas on the returned image.
   :returns: List of bounding boxes ``[[x1, y1, x2, y2], ...]``.
   :rtype: list[list[int]]

----

locate_image_center
===================

.. function:: locate_image_center(image, detect_threshold=1, draw_image=False)

   Locates a template image and returns its center position.

   :param image: Template image to search for (file path or PIL image).
   :type image: str or PIL.Image
   :param float detect_threshold: Detection precision from ``0.0`` to ``1.0``.
   :param bool draw_image: If ``True``, marks detected areas on the returned image.
   :returns: Center coordinates ``(x, y)``.
   :rtype: list[int, int]

----

locate_and_click
================

.. function:: locate_and_click(image, mouse_keycode, detect_threshold=1, draw_image=False)

   Locates a template image and clicks on its center position.

   :param image: Template image to search for (file path or PIL image).
   :type image: str or PIL.Image
   :param mouse_keycode: Mouse button to click (e.g., ``"mouse_left"``).
   :type mouse_keycode: int or str
   :param float detect_threshold: Detection precision from ``0.0`` to ``1.0``.
   :param bool draw_image: If ``True``, marks detected areas on the returned image.
   :returns: Center coordinates ``(x, y)`` of the clicked image.
   :rtype: list[int, int]

----

screenshot
==========

.. function:: screenshot(file_path=None, region=None)

   Captures the current screen.

   :param str file_path: Path to save the screenshot. If ``None``, the image is not saved to disk.
   :param list region: Screen region to capture as ``[x1, y1, x2, y2]``.
      If ``None``, captures the full screen.
   :returns: The captured screen image.
   :rtype: PIL.Image
