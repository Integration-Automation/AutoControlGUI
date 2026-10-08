=============
Mouse Control
=============

AutoControl provides functions for simulating mouse actions including clicking,
positioning, scrolling, and drag operations.

Getting Mouse Button Table
==========================

Retrieve all available mouse button key names:

.. code-block:: python

   from je_auto_control import mouse_table

   print(mouse_table)

.. tip::

   See :doc:`/API/special/mouse_keys` for the full list of available mouse keys per platform.

Press and Release
=================

Hold down a mouse button and release it after a delay:

.. code-block:: python

   from time import sleep
   from je_auto_control import press_mouse, release_mouse

   press_mouse("mouse_right")
   sleep(1)
   release_mouse("mouse_right")

Click
=====

Press and immediately release a mouse button:

.. code-block:: python

   from je_auto_control import click_mouse

   # Right click at current position
   click_mouse("mouse_right")

   # Left click at specific coordinates
   click_mouse("mouse_left", x=500, y=300)

   # Double-click: two clicks on the same point, 60 ms apart
   click_mouse("mouse_left", x=500, y=300, clicks=2, interval=0.06)

Windows and X11 recognise a double-click from the timing and distance of the
clicks, so keep ``interval`` under the system double-click time (500 ms by
default on Windows). macOS applications read a click count carried by the
event instead, so there the n-th click has its click-state field
(``kCGMouseEventClickState``) set to n; when ``interval`` is longer than the
system double-click interval every click is sent as a single click.

Position
========

Get and set the mouse cursor position:

.. code-block:: python

   from je_auto_control import get_mouse_position, set_mouse_position

   # Get current position
   x, y = get_mouse_position()
   print(f"Mouse at: ({x}, {y})")

   # Move mouse to (100, 100)
   set_mouse_position(100, 100)

Scroll
======

Scroll the mouse wheel:

.. code-block:: python

   from je_auto_control import mouse_scroll

   # Scroll down by 5 units
   mouse_scroll(scroll_value=5)

.. note::

   On Linux, you can specify the scroll direction using the ``scroll_direction`` parameter:
   ``"scroll_up"``, ``"scroll_down"``, ``"scroll_left"``, ``"scroll_right"``.
