Held Modifiers Across an Action Group
=====================================

``hotkey`` presses a set of keys and releases them immediately — fine for a
one-shot chord, but there was no way to hold ``ctrl`` (or ``shift``) *down across
several independent actions* (range-select with shift-clicks, ctrl-clicks to
multi-select) and be sure the modifiers are released even if one of those actions
raises.

:func:`plan_with_modifiers` wraps an op-step list with press / release steps and
is pure / unit-testable; :func:`hold_modifiers` is a context manager that presses
on enter and releases (in reverse) on exit — including on exception —
dispatching through an injectable ``sink``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import hold_modifiers, plan_with_modifiers
    from je_auto_control import click_mouse

    # shift-held range select: every click happens with shift down
    with hold_modifiers(["shift"]):
        click_mouse("mouse_left", 100, 100)
        click_mouse("mouse_left", 100, 300)
    # shift is released here — even if a click raised

    plan_with_modifiers([{"op": "click"}], ["ctrl", "shift"])
    # press ctrl, press shift, click, release shift, release ctrl

Modifiers are pressed in order on entry and released in *reverse* order on exit,
in a ``finally`` block, so a stuck modifier can never leak. ``plan_with_modifiers``
is the pure plan for any op-step list.

Executor commands
-----------------

``AC_with_modifiers`` runs a nested JSON action list while ``modifiers`` (e.g.
``["ctrl"]`` or ``"ctrl+shift"``) are held, releasing them even if an action
fails. It is exposed as the MCP tool ``ac_with_modifiers`` and as a Script
Builder command under **Keyboard**.
