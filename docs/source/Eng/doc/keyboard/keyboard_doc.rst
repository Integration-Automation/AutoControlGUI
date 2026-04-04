================
Keyboard Control
================

AutoControl provides functions for simulating keyboard input including key press/release,
typing strings, hotkey combinations, and key state detection.

Getting Key Tables
==================

Retrieve available key names:

.. code-block:: python

   from je_auto_control import keys_table, get_special_table

   # All available keys for your platform
   print(keys_table)

   # Special keys (platform-specific)
   print(get_special_table())

.. tip::

   See :doc:`/API/special/keyboard_keys` for the full list of available keyboard keys per platform.

Press and Release
=================

Hold a key down and release it after a delay:

.. code-block:: python

   from time import sleep
   from je_auto_control import press_keyboard_key, release_keyboard_key

   press_keyboard_key("a")
   sleep(1)
   release_keyboard_key("a")

Type a Single Key
=================

Press and immediately release a key:

.. code-block:: python

   from je_auto_control import type_keyboard

   type_keyboard("a")

Check Key State
===============

Check whether a specific key is currently pressed:

.. code-block:: python

   from je_auto_control import check_key_is_press

   is_pressed = check_key_is_press("a")
   print(f"Key 'a' is pressed: {is_pressed}")

Type a String
=============

Type a sequence of characters one by one:

.. code-block:: python

   from je_auto_control import write

   write("Hello World")

Hotkey Combinations
===================

Press multiple keys in sequence, then release them in reverse order:

.. code-block:: python

   import sys
   from je_auto_control import hotkey

   if sys.platform in ["win32", "cygwin", "msys"]:
       hotkey(["lcontrol", "a", "lcontrol", "c", "lcontrol", "v"])

   elif sys.platform == "darwin":
       hotkey(["command", "a", "command", "c", "command", "v"])

   elif sys.platform in ["linux", "linux2"]:
       hotkey(["ctrl", "a", "ctrl", "c", "ctrl", "v"])

.. warning::

   Key names differ across platforms. Always check the key table for your target platform.
