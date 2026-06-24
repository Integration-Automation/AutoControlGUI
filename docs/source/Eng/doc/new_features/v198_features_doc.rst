Move / Resize Elements + Window State (UIA Transform + Window)
==============================================================

This is **UIA-element-level**, not the HWND / title-level geometry in
``window_layout`` / ``window_geometry``. ``TransformPattern`` moves and resizes a
specific control or floating panel (dockable toolbars, MDI children, splitters)
that has no top-level window of its own; ``WindowPattern`` minimizes / maximizes a
window and — most usefully — reports its **interaction state**, a reliable "is
this window ready or modal-blocked?" signal that pixel or title polling can't give.

* :func:`move_element` / :func:`resize_element` — TransformPattern,
* :func:`set_window_state` — minimize / maximize / restore,
* :func:`window_interaction_state` — the readiness / modal-blocked signal.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real UIA calls live in the
Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (move_element, resize_element,
                                 set_window_state, window_interaction_state)

    move_element(100, 200, name="Tool Palette")     # reposition a floating panel
    resize_element(640, 480, name="Preview")        # resize a control
    set_window_state("maximized", name="Editor")    # normal / maximized / minimized

    if window_interaction_state(name="Editor") == "ready":
        ...   # not "blocked_by_modal" / "not_responding" — safe to drive

The element / window is located by ``name`` / ``role`` / ``app_name`` /
``automation_id`` (same as the other native-control actions). The actions return
``bool``; ``window_interaction_state`` returns ``ready`` / ``blocked_by_modal`` /
``not_responding`` / ``running`` / ``closing`` (or ``None`` if not found).

Executor commands
-----------------

``AC_move_element`` (``x`` / ``y``), ``AC_resize_element`` (``width`` /
``height``), ``AC_set_window_state`` (``state``) and
``AC_window_interaction_state`` (``{state}``). They are exposed as the matching
``ac_*`` MCP tools (the actions destructive, the read read-only) and as Script
Builder commands under **Native UI**.
