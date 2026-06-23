Relative Mouse Movement
=======================

The mouse wrapper exposes only absolute ``set_mouse_position`` — there was no
"nudge the pointer by ``(dx, dy)``" (the pynput / PyAutoGUI ``moveRel`` staple),
which relative-pointer / canvas / FPS-style apps and incremental drags need.

:func:`relative_target` is the pure arithmetic (current + delta) and is
unit-testable; :func:`move_mouse_relative` reads the live position and sets the
new one, with both the getter and setter injectable so it is tested without a
real pointer. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import move_mouse_relative, relative_target

    move_mouse_relative(-40, 12)        # nudge left 40, down 12 from where it is
    # {'from': [200, 200], 'to': [160, 212], 'delta': [-40, 12]}

    relative_target((100, 100), 10, -5)   # (110, 95) — pure, no I/O

``move_mouse_relative`` reads the current position (raising
``AutoControlMouseException`` if it cannot), adds the delta, and moves there.
``get_position`` / ``set_position`` default to the real mouse wrapper but are
injectable for headless tests.

Executor commands
-----------------

``AC_move_mouse_relative`` takes ``dx`` / ``dy`` and returns ``{from, to,
delta}``. It is exposed as the MCP tool ``ac_move_mouse_relative`` and as a
Script Builder command under **Mouse**.
