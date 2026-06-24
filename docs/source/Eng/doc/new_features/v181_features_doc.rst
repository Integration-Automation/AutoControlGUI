Extended UIA Control Patterns (Expand / Select / Range / Scroll)
===============================================================

The accessibility backend shipped only four control patterns — Value, Invoke, Toggle and a
read-only Grid dump. That left the controls automation hits most often undriveable by their
*native* pattern: a treeview node could not be expanded, a listbox / combobox item could not be
selected (SelectionItemPattern), a slider could not be set (RangeValuePattern), and a control
could not be scrolled into view (ScrollItemPattern) — those fell back to fragile pixel guessing.
``control_patterns`` adds those object-level actions on top of the existing accessibility
backend ABC.

Each function is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam (the same seam the rest of the accessibility module uses), so the headless core is
unit-testable on any platform by injecting a fake backend; the real UI Automation calls live in
the Windows backend (ExpandCollapse / SelectionItem / RangeValue / ScrollItem patterns).
Backends that don't implement a pattern raise ``AccessibilityNotAvailableError``. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (expand_control, collapse_control,
                                 control_expand_state, select_control_item,
                                 control_range, set_control_range,
                                 scroll_control_into_view)

    expand_control(name="Documents", role="treeitem")     # open a tree node
    select_control_item(name="Option B")                  # pick a list/combo item
    set_control_range(75, name="Volume")                  # set a slider
    print(control_range(name="Volume"))   # {"value": 75.0, "minimum": 0, "maximum": 100}
    scroll_control_into_view(name="Row 200")              # bring a row on-screen

All locate the control by ``name`` / ``role`` / ``app_name`` / ``automation_id`` (same as the
existing ``control_invoke`` / ``control_toggle``). The expand/select/scroll/set actions return
``bool``; ``control_expand_state`` returns ``expanded`` / ``collapsed`` / ``partial`` / ``leaf``
(or ``None``); ``control_range`` returns ``{value, minimum, maximum}`` (or ``None``).

Executor commands
-----------------

``AC_expand_control`` / ``AC_collapse_control`` / ``AC_control_expand_state`` /
``AC_select_control_item`` / ``AC_control_range`` / ``AC_set_control_range`` /
``AC_scroll_control_into_view``. They are exposed as the matching ``ac_*`` MCP tools (the action
ones destructive, the reads read-only) and as Script Builder commands under **Native UI**.
