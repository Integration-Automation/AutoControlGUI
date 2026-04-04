==========
Screen API
==========

Functions for screen information and capture.

----

screen_size
===========

.. function:: screen_size()

   Returns the current screen resolution.

   :returns: Screen dimensions as ``(width, height)``.
   :rtype: tuple[int, int]

----

screenshot
==========

.. function:: screenshot(file_path=None, screen_region=None)

   Captures the current screen image.

   :param str file_path: File path to save the screenshot. If ``None``, the image is not saved.
   :param list screen_region: Region to capture as ``[x1, y1, x2, y2]``.
      If ``None``, captures the full screen.
   :returns: The captured screen image.
   :rtype: list[int]
