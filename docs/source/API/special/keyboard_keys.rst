=============
Keyboard Keys
=============

Keyboard key names available per platform. Use these names as the ``keycode`` parameter
in keyboard functions.

.. note::

   Key names are **platform-specific**. Always check the table for your target platform.
   Use ``keys_table`` and ``get_special_table()`` at runtime to get the exact keys
   available on the current system.

Windows
=======

Common keys:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Key Name
     - Description
   * - ``a`` - ``z``
     - Letter keys
   * - ``0`` - ``9``
     - Number keys
   * - ``f1`` - ``f24``
     - Function keys
   * - ``enter``, ``return``
     - Enter / Return
   * - ``tab``
     - Tab
   * - ``space``
     - Space bar
   * - ``back``
     - Backspace
   * - ``escape``
     - Escape
   * - ``lcontrol``, ``rcontrol``
     - Left / Right Control
   * - ``lshift``, ``rshift``
     - Left / Right Shift
   * - ``lalt``, ``ralt``
     - Left / Right Alt
   * - ``lwin``, ``rwin``
     - Left / Right Windows key
   * - ``up``, ``down``, ``left``, ``right``
     - Arrow keys
   * - ``insert``, ``delete``
     - Insert / Delete
   * - ``home``, ``end``
     - Home / End
   * - ``pageup``, ``pagedown``
     - Page Up / Page Down
   * - ``capslock``
     - Caps Lock
   * - ``numlock``
     - Num Lock
   * - ``print_screen``
     - Print Screen
   * - ``numpad0`` - ``numpad9``
     - Numpad keys
   * - ``add``, ``subtract``, ``multiply``, ``divide``
     - Numpad operators
   * - ``apps``
     - Application / Menu key
   * - ``browser_back``, ``browser_forward``
     - Browser navigation keys
   * - ``volume_mute``, ``volume_up``, ``volume_down``
     - Volume control keys

.. tip::

   For the complete list of 200+ Windows keys, use ``keys_table`` at runtime:

   .. code-block:: python

      from je_auto_control import keys_table
      for key_name in sorted(keys_table.keys()):
          print(key_name)

Linux (X11)
===========

Common keys:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Key Name
     - Description
   * - ``a`` - ``z``
     - Letter keys
   * - ``0`` - ``9``
     - Number keys
   * - ``f1`` - ``f12``
     - Function keys
   * - ``return``
     - Enter / Return
   * - ``tab``
     - Tab
   * - ``space``
     - Space bar
   * - ``backspace``
     - Backspace
   * - ``escape``
     - Escape
   * - ``ctrl``, ``ctrl_r``
     - Left / Right Control
   * - ``shift``, ``shift_r``
     - Left / Right Shift
   * - ``alt``, ``alt_r``
     - Left / Right Alt
   * - ``super``, ``super_r``
     - Left / Right Super (Windows) key
   * - ``up``, ``down``, ``left``, ``right``
     - Arrow keys
   * - ``insert``, ``delete``
     - Insert / Delete
   * - ``home``, ``end``
     - Home / End
   * - ``page_up``, ``page_down``
     - Page Up / Page Down
   * - ``caps_lock``
     - Caps Lock
   * - ``num_lock``
     - Num Lock

.. tip::

   Linux supports 380+ key codes. Use ``keys_table`` at runtime for the complete list.

macOS
=====

Common keys:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Key Name
     - Description
   * - ``a`` - ``z``
     - Letter keys (mapped to macOS virtual key codes)
   * - ``0`` - ``9``
     - Number keys
   * - ``f1`` - ``f20``
     - Function keys
   * - ``return``
     - Enter / Return
   * - ``tab``
     - Tab
   * - ``space``
     - Space bar
   * - ``delete``
     - Backspace / Delete
   * - ``escape``
     - Escape
   * - ``command``
     - Command key
   * - ``shift``, ``shift_r``
     - Left / Right Shift
   * - ``option``, ``option_r``
     - Left / Right Option (Alt)
   * - ``control``
     - Control
   * - ``up``, ``down``, ``left``, ``right``
     - Arrow keys
   * - ``home``, ``end``
     - Home / End
   * - ``page_up``, ``page_down``
     - Page Up / Page Down
   * - ``caps_lock``
     - Caps Lock
   * - ``volume_up``, ``volume_down``, ``mute``
     - Volume control keys

.. tip::

   macOS supports 170+ key codes. Use ``keys_table`` at runtime for the complete list.
