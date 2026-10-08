=========
Mouse API
=========

Functions for controlling the mouse cursor.

----

get_mouse_table
===============

.. function:: get_mouse_table()

   Returns the mouse key table for the current platform.

   :returns: Dictionary mapping mouse button names to platform-specific key codes.
   :rtype: dict

----

mouse_preprocess
================

.. function:: mouse_preprocess(mouse_keycode, x, y)

   Validates the mouse key code and resolves the cursor position.
   If ``x`` or ``y`` is ``None``, the current mouse position is used.

   :param mouse_keycode: Mouse button name or key code.
   :type mouse_keycode: int or str
   :param x: X coordinate. If ``None``, uses current position.
   :type x: int
   :param y: Y coordinate. If ``None``, uses current position.
   :type y: int
   :returns: Tuple of ``(keycode, x, y)``.
   :rtype: tuple

----

get_mouse_position
==================

.. function:: get_mouse_position()

   Returns the current mouse cursor position.

   :returns: Tuple of ``(x, y)``.
   :rtype: tuple[int, int]

----

set_mouse_position
==================

.. function:: set_mouse_position(x, y)

   Moves the mouse cursor to the specified coordinates.

   :param int x: Target X position.
   :param int y: Target Y position.
   :returns: Tuple of ``(x, y)``.
   :rtype: tuple[int, int]

----

press_mouse
===========

.. function:: press_mouse(mouse_keycode, x=None, y=None)

   Presses and holds a mouse button at the specified position.

   :param mouse_keycode: Mouse button name (e.g., ``"mouse_left"``).
   :type mouse_keycode: int or str
   :param int x: X position (default: current position).
   :param int y: Y position (default: current position).
   :returns: Tuple of ``(keycode, x, y)``.
   :rtype: tuple

----

release_mouse
=============

.. function:: release_mouse(mouse_keycode, x=None, y=None)

   Releases a previously pressed mouse button.

   :param mouse_keycode: Mouse button name (e.g., ``"mouse_left"``).
   :type mouse_keycode: int or str
   :param int x: X position (default: current position).
   :param int y: Y position (default: current position).
   :returns: Tuple of ``(keycode, x, y)``.
   :rtype: tuple

----

click_mouse
===========

.. function:: click_mouse(mouse_keycode, x=None, y=None, clicks=1, interval=0.0)

   Presses and releases a mouse button at the specified position, ``clicks``
   times, ``interval`` seconds apart; ``clicks=2`` double-clicks. Windows and
   X11 recognise a double-click from the timing and distance of the clicks, so
   keep ``interval`` under the system double-click time. macOS applications
   read a click count carried by the event instead, so there the n-th click
   has its click-state field (``kCGMouseEventClickState``) set to n; when
   ``interval`` is longer than the system double-click interval every click is
   sent as a single click.

   :param mouse_keycode: Mouse button name (e.g., ``"mouse_left"``).
   :type mouse_keycode: int or str
   :param int x: X position (default: current position).
   :param int y: Y position (default: current position).
   :param int clicks: Number of clicks, at least 1 (default: 1).
   :param float interval: Seconds between clicks, at least 0 (default: 0.0).
   :raises AutoControlMouseException: on an invalid ``clicks`` or ``interval``.
   :returns: Tuple of ``(keycode, x, y)``.
   :rtype: tuple

----

mouse_scroll
============

.. function:: mouse_scroll(scroll_value, x=None, y=None, scroll_direction="scroll_down")

   Scrolls the mouse wheel.

   :param int scroll_value: Number of scroll units.
   :param int x: X position (default: current position).
   :param int y: Y position (default: current position).
   :param str scroll_direction: Scroll direction (Linux only). One of:
      ``"scroll_up"``, ``"scroll_down"``, ``"scroll_left"``, ``"scroll_right"``.
   :returns: Tuple of ``(scroll_value, direction)``.
   :rtype: tuple
