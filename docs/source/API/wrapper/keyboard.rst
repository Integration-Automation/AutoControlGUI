============
Keyboard API
============

Functions for simulating keyboard input.

----

get_special_table
=================

.. function:: get_special_table()

   Returns the special keyboard keys table for the current platform.

   :returns: Dictionary of special key names to key codes.
   :rtype: dict

   .. note:: Not every platform has special keys.

----

get_keyboard_keys_table
=======================

.. function:: get_keyboard_keys_table()

   Returns the full keyboard keys table for the current platform.

   :returns: Dictionary of key names to key codes.
   :rtype: dict

----

keyboard_key_name
=================

.. function:: keyboard_key_name(keycode)

   Returns the canonical name of a key code, for recorders and anything else
   that turns a captured virtual key back into a name. A code often has
   several names in the table; aliases (``esc`` for ``escape``, listed in
   ``platform_wrapper.keyboard_key_aliases``) never answer, so adding one
   cannot change the names a recording writes. Among the rest, a name of
   lower-case letters, digits and underscores wins, then the shortest, then
   the alphabetically first.

   :param int keycode: Platform key code (a Win32 virtual key on Windows).
   :returns: The name, e.g. ``"escape"`` for 27 on Windows, or ``None`` when
      the table has no name for the code.
   :rtype: str or None

----

press_keyboard_key
==================

.. function:: press_keyboard_key(keycode, is_shift=False, skip_record=False)

   Presses and holds a keyboard key. Use :func:`release_keyboard_key` to release it.

   :param keycode: Key name or key code to press.
   :type keycode: int or str
   :param bool is_shift: Whether to press Shift simultaneously.
   :param bool skip_record: If ``True``, this action will not be recorded.
   :returns: The key code that was pressed.
   :rtype: str

----

release_keyboard_key
====================

.. function:: release_keyboard_key(keycode, is_shift=False, skip_record=False)

   Releases a previously pressed keyboard key.

   :param keycode: Key name or key code to release.
   :type keycode: int or str
   :param bool is_shift: Whether Shift was pressed.
   :param bool skip_record: If ``True``, this action will not be recorded.
   :returns: The key code that was released.
   :rtype: str

----

type_keyboard
=============

.. function:: type_keyboard(keycode, is_shift=False, skip_record=False)

   Presses and immediately releases a keyboard key.

   :param keycode: Key name or key code to type.
   :type keycode: int or str
   :param bool is_shift: Whether to press Shift simultaneously.
   :param bool skip_record: If ``True``, this action will not be recorded.
   :returns: The key code that was typed.
   :rtype: str

----

check_key_is_press
==================

.. function:: check_key_is_press(keycode)

   Checks whether a specific key is currently pressed.

   :param keycode: Key name or key code to check.
   :type keycode: int or str
   :returns: ``True`` if the key is pressed, ``False`` otherwise.
   :rtype: bool
