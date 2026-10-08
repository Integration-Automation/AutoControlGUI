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

On Windows the table also accepts common aliases (``ctrl``, ``alt``, ``enter``,
``esc``, ``win``, ``backspace``, ``del``, ``pgup``, ``capslock``, ``prtsc``,
``numpad0`` ...). To turn a captured key code back into a name, use
``keyboard_key_name``; it always answers with the canonical name, never an
alias:

.. code-block:: python

   from je_auto_control import keyboard_key_name

   keyboard_key_name(27)     # "escape" on Windows
   keyboard_key_name(0xBB)   # "oem_plus"

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

A capital letter is typed as a capital: ``write`` holds Shift around it on
Windows and X11 (it used to arrive in lower case). A Windows line ending
(CR LF) is one line break and presses Enter once, not twice. ``is_shift=True``
holds Shift for every key, and does so on every platform; the same is true of
``type_keyboard``, ``press_keyboard_key`` and ``hotkey``, where it used to be
ignored outside macOS.

``write`` logs the text, records it in the test record and returns it. For a
password or token use ``write_secret`` (``AC_write_secret`` with ``secret``):
the log gets the length only, the record a masked value, it returns nothing, and
an error never names a character. It types every character as a Unicode key
event, so the text arrives exactly whatever the layout and Caps Lock say (line
breaks, Tab and Backspace are pressed as keys); a backend without Unicode typing
(only Windows has it) refuses before typing anything.

.. code-block:: python

   import os
   from je_auto_control import write_secret

   write_secret(os.environ["APP_PASSWORD"])

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
