"""MSAA bridge for old controls UIA can't model (LegacyIAccessiblePattern).

Many legacy Win32 / MFC / Delphi controls expose **nothing useful** via the modern
UIA patterns — ``control_get_value`` / ``control_invoke`` / ``control_toggle`` all
return None / do nothing — yet they are fully described through the MSAA
``IAccessible`` bridge: a Name, Value, Description, Role, State and a
**DefaultAction**. ``legacy_accessible`` is the last-resort fallback that still
reads that info and fires the default action, making the long tail of old apps
automatable.

* :func:`legacy_info` — the MSAA fields ``{name, value, description,
  default_action, role, state}``,
* :func:`legacy_default_action` — fire the control's default action.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable via a fake backend; the real ``LegacyIAccessiblePattern``
calls live in the Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional


def legacy_info(name: Optional[str] = None, role: Optional[str] = None,
                app_name: Optional[str] = None,
                automation_id: Optional[str] = None,
                ) -> Optional[Dict[str, Any]]:
    """Return the MSAA ``IAccessible`` info of an old control, or None if absent."""
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend().legacy_info(name=name, role=role, app_name=app_name,
                                     automation_id=automation_id)


def legacy_default_action(name: Optional[str] = None, role: Optional[str] = None,
                          app_name: Optional[str] = None,
                          automation_id: Optional[str] = None) -> bool:
    """Fire an old control's MSAA default action (the Value/Invoke/Toggle fallback)."""
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend().legacy_default_action(name=name, role=role,
                                               app_name=app_name,
                                               automation_id=automation_id)
