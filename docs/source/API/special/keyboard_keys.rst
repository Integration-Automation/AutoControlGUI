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

Common keys. The first name is the Win32 one a reverse lookup
(``keyboard_key_name``) returns; the others are aliases for the same key:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Key Name
     - Description
   * - ``a`` - ``z``
     - Letter keys
   * - ``0`` - ``9``
     - Number keys
   * - ``f1`` - ``f24``
     - Function keys
   * - ``return``, ``enter``
     - Enter / Return
   * - ``tab``
     - Tab
   * - ``space``
     - Space bar
   * - ``back``, ``backspace``, ``bksp``
     - Backspace
   * - ``escape``, ``esc``
     - Escape
   * - ``control``, ``ctrl``; ``lcontrol``, ``lctrl``; ``rcontrol``, ``rctrl``
     - Control, left / right Control
   * - ``shift``, ``lshift``, ``rshift``
     - Shift, left / right Shift
   * - ``menu``, ``alt``; ``lmenu``, ``lalt``; ``rmenu``, ``ralt``
     - Alt, left / right Alt
   * - ``lwin``, ``win``, ``super``, ``cmd``, ``meta``; ``rwin``
     - Left / right Windows key
   * - ``up``, ``down``, ``left``, ``right``
     - Arrow keys
   * - ``insert``, ``ins``; ``delete``, ``del``
     - Insert / Delete
   * - ``home``, ``end``
     - Home / End
   * - ``prior``, ``pgup``, ``pageup``; ``next``, ``pgdn``, ``pagedown``
     - Page Up / Page Down
   * - ``capital``, ``caps``, ``capslock``
     - Caps Lock
   * - ``numlock``; ``scroll``, ``scrolllock``
     - Num Lock / Scroll Lock
   * - ``snapshot``, ``printscreen``, ``prtsc``, ``prtscr``
     - Print Screen
   * - ``num0`` - ``num9``, ``numpad0`` - ``numpad9``
     - Numpad keys
   * - ``add``, ``subtract``, ``multiply``, ``divide``, ``decimal``
     - Numpad operators
   * - ``oem_plus``, ``plus``; ``oem_comma``, ``comma``; ``oem_minus``, ``minus``; ``oem_period``, ``period``
     - ``=`` / ``,`` / ``-`` / ``.`` keys, the same key on every layout
   * - ``oem_1`` - ``oem_8``, ``oem_102``
     - Punctuation keys whose character depends on the layout (``oem_1`` is
       ``;`` on a US layout); they have no character-named alias on purpose
   * - ``oem_clear``
     - Clear
   * - ``apps``
     - Application / Menu key
   * - ``browser_back``, ``browser_forward``, ``browser_home``
     - Browser navigation keys
   * - ``launch_app1``, ``launch_app2``
     - Launch application keys (``LAUNCH_APP2`` also still works)
   * - ``volume_mute``, ``volume_up``, ``volume_down``
     - Volume control keys

.. tip::

   For the complete list of 200+ Windows keys, use ``keys_table`` at runtime:

   .. code-block:: python

      from je_auto_control import keyboard_keys_table
      for key_name in sorted(keyboard_keys_table.keys()):
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
