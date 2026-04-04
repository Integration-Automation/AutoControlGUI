===========
Quick Start
===========

This guide walks you through the most common AutoControl features with minimal examples.

Mouse Control
=============

.. code-block:: python

   import je_auto_control

   # Get current mouse position
   x, y = je_auto_control.get_mouse_position()
   print(f"Mouse at: ({x}, {y})")

   # Move mouse to coordinates
   je_auto_control.set_mouse_position(500, 300)

   # Left click at current position
   je_auto_control.click_mouse("mouse_left")

   # Right click at specific coordinates
   je_auto_control.click_mouse("mouse_right", x=800, y=400)

   # Scroll down
   je_auto_control.mouse_scroll(scroll_value=5)

Keyboard Control
================

.. code-block:: python

   import je_auto_control

   # Press and release a single key
   je_auto_control.type_keyboard("a")

   # Type a whole string character by character
   je_auto_control.write("Hello World")

   # Hotkey combination (e.g., Ctrl+C)
   je_auto_control.hotkey(["ctrl_l", "c"])

   # Check if a key is currently pressed
   is_pressed = je_auto_control.check_key_is_press("shift_l")

Image Recognition
=================

.. code-block:: python

   import je_auto_control

   # Find all occurrences of an image on screen
   positions = je_auto_control.locate_all_image("button.png", detect_threshold=0.9)

   # Find a single image and get its center coordinates
   cx, cy = je_auto_control.locate_image_center("icon.png", detect_threshold=0.85)

   # Find an image and automatically click it
   je_auto_control.locate_and_click("submit_button.png", mouse_keycode="mouse_left")

Screenshot
==========

.. code-block:: python

   import je_auto_control

   # Full-screen screenshot
   je_auto_control.pil_screenshot("screenshot.png")

   # Screenshot of a specific region [x1, y1, x2, y2]
   je_auto_control.pil_screenshot("region.png", screen_region=[100, 100, 500, 400])

   # Get screen resolution
   width, height = je_auto_control.screen_size()

Action Recording & Playback
============================

.. code-block:: python

   import je_auto_control
   import time

   je_auto_control.record()
   time.sleep(10)  # Record for 10 seconds
   actions = je_auto_control.stop_record()

   # Replay the recorded actions
   je_auto_control.execute_action(actions)

JSON Action Scripting
=====================

Create a JSON action file (``actions.json``):

.. code-block:: json

   [
       ["AC_set_mouse_position", {"x": 500, "y": 300}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
       ["AC_write", {"write_string": "Hello from AutoControl"}],
       ["AC_hotkey", {"key_code_list": ["ctrl_l", "s"]}]
   ]

Execute it:

.. code-block:: python

   import je_auto_control

   je_auto_control.execute_action(
       je_auto_control.read_action_json("actions.json")
   )

What's Next?
============

* See the :doc:`../Eng/eng_index` for detailed guides on each feature.
* See the :doc:`../API/api_index` for complete API reference.
