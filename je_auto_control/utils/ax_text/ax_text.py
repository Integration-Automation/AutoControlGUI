"""Native text reading via the UI Automation TextPattern.

``control_get_value`` reads a control through ValuePattern, but ValuePattern
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
platform by injecting a fake backend; the real UIA calls live in the Windows
backend. Imports no ``PySide6``.
"""
from typing import Optional


def _backend():
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend()


def get_control_text(name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[str]:
    """Return a control's full text via TextPattern (``None`` if not found).

    Unlike :func:`control_get_value`, this works on multiline edits, RichEdit /
    document controls and web text areas where ValuePattern returns ``""``.
    """
    return _backend().document_text(name=name, role=role, app_name=app_name,
                                    automation_id=automation_id)


def get_selected_text(name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Optional[str]:
    """Return the control's currently selected text (TextPattern.GetSelection).

    Empty string when nothing is selected; ``None`` if the control is not found
    or exposes no TextPattern.
    """
    return _backend().selected_text(name=name, role=role, app_name=app_name,
                                    automation_id=automation_id)


def get_visible_text(name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[str]:
    """Return only the on-screen text of a control (TextPattern.GetVisibleRanges).

    Useful for scrolled documents where :func:`get_control_text` would return the
    whole (possibly huge) buffer. ``None`` if the control is not found.
    """
    return _backend().visible_text(name=name, role=role, app_name=app_name,
                                   automation_id=automation_id)
