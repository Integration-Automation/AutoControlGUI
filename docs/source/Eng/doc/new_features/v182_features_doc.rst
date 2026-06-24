Native Text Reading via the UIA TextPattern (document / selection / visible)
============================================================================

``control_get_value`` reads a control through UIA ValuePattern, but ValuePattern
returns an **empty string** on multiline edits, RichEdit / document controls and
web text areas — exactly the controls whose text you most want to read. UIA
exposes that text through a different pattern, ``TextPattern``, which models the
control's content as text ranges. ``ax_text`` adds three reads on top of the
existing accessibility backend ABC:

* :func:`get_control_text` — the whole document's text (``DocumentRange``),
* :func:`get_selected_text` — the currently selected text (``GetSelection``),
* :func:`get_visible_text` — only the on-screen text (``GetVisibleRanges``).

Each function is a thin dispatch onto the injectable
``accessibility.backends.get_backend()`` seam (the same seam the rest of the
accessibility module uses), so the headless core is unit-testable on any
platform by injecting a fake backend; the real UI Automation calls live in the
Windows backend. Backends that don't implement TextPattern raise
``AccessibilityNotAvailableError``. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (get_control_text, get_selected_text,
                                 get_visible_text)

    # A multiline editor where control_get_value returns "" :
    text = get_control_text(name="Editor", role="document")
    selection = get_selected_text(name="Editor")   # "" when nothing selected
    on_screen = get_visible_text(name="Editor")    # skips scrolled-off lines

All locate the control by ``name`` / ``role`` / ``app_name`` / ``automation_id``
(same as ``control_get_value`` / ``control_invoke``). Each returns the text as a
``str``, or ``None`` when the control is not found or exposes no TextPattern;
``get_selected_text`` returns ``""`` when the control is found but has no
selection.

Executor commands
-----------------

``AC_get_control_text`` / ``AC_get_selected_text`` / ``AC_get_visible_text`` each
return ``{"text": ...}``. They are exposed as the matching read-only ``ac_*`` MCP
tools and as Script Builder commands under **Native UI**.
