=============
Critical Exit
=============

Critical Exit is a safety mechanism that allows you to forcibly stop an automation script
by pressing a hotkey (default: **F7**).

.. warning::

   Critical Exit is **disabled by default**. Enabling it consumes additional system resources
   as it runs a background thread that continuously monitors the keyboard.

Enabling Critical Exit
======================

.. code-block:: python

   from je_auto_control import CriticalExit

   CriticalExit().init_critical_exit()

After calling ``init_critical_exit()``, pressing **F7** will interrupt the main thread
and terminate the program.

Changing the Hotkey
===================

.. code-block:: python

   from je_auto_control import CriticalExit

   critical = CriticalExit()
   critical.set_critical_key("escape")  # Use Escape instead of F7
   critical.init_critical_exit()

Example: Recovering from Runaway Mouse
=======================================

.. code-block:: python

   import sys
   from je_auto_control import (
       CriticalExit, AutoControlMouseException,
       set_mouse_position, screen_size, press_keyboard_key
   )

   print(screen_size())

   try:
       while True:
           set_mouse_position(200, 400)
           set_mouse_position(400, 600)
           raise AutoControlMouseException
   except Exception as error:
       print(repr(error), file=sys.stderr)
       CriticalExit().init_critical_exit()
       press_keyboard_key("f7")

.. danger::

   Be extremely careful when testing automation loops that move the mouse continuously.
   Always have Critical Exit enabled or another way to regain control.
