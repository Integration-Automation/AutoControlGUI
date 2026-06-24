Keyboard Focus Order (Tab sequence / WCAG audit / set-focus)
============================================================

Nothing in the toolkit reasoned about *keyboard* navigation — only mouse
coordinates and element values. ``focus_order`` adds the keyboard layer:

* :func:`is_interactive_role` — is a role one that normally takes keyboard focus,
* :func:`tab_order` — the focusable elements in the order ``Tab`` will visit them
  (their reading order: top-to-bottom, left-to-right),
* :func:`audit_focus_order` — a WCAG 2.4.x focus-order report over a flat element
  list (the sequence plus flagged problems, e.g. a focusable element with no
  visible area — focus would land somewhere unseen),
* :func:`focus_control` — set the keyboard focus on a control (UIA ``SetFocus``).

The first three are pure functions over ``AccessibilityElement`` lists:
``tab_order`` reuses ``element_parse.reading_order`` for row banding and
``is_interactive_role`` reuses ``ax_tree_walk.humanize_role``, so no logic is
duplicated. ``focus_control`` is a thin dispatch onto the injectable
``accessibility.backends.get_backend()`` seam; the real ``SetFocus`` lives in the
Windows backend. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (list_accessibility_elements, tab_order,
                                 audit_focus_order, focus_control)

    elements = list_accessibility_elements(app_name="myapp.exe")
    for el in tab_order(elements):           # the Tab visiting order
        print(el.name, el.role)

    report = audit_focus_order(elements)
    # {"order": [...], "issues": [...], "focusable_count": N, "issue_count": M}

    focus_control(name="Username", role="edit")   # put the cursor in the field

Focusability is role-based (the interactive roles: Button, Edit, CheckBox,
ComboBox, RadioButton, Hyperlink, ListItem, MenuItem, Slider, Tab/TabItem,
TreeItem, …). ``focus_control`` locates by ``name`` / ``role`` / ``app_name`` /
``automation_id`` like the other native-control actions and returns ``bool``.

Executor commands
-----------------

``AC_tab_order`` / ``AC_audit_focus_order`` (``app_name`` / ``max_results``) list
and audit the live app; ``AC_focus_control`` sets focus. They are exposed as the
matching ``ac_*`` MCP tools (the two reads read-only, ``ac_focus_control``
destructive) and as Script Builder commands under **Native UI**.
