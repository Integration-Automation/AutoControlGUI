"""Read rich UI Automation properties the flat element list omits.

``list_accessibility_elements`` / ``AccessibilityElement`` carry only name / role /
bounds / app / pid / automation_id. Automation routinely needs more before it
acts: **is the control enabled** (don't click a disabled button), **is it
off-screen** (is it really visible?), its **item_status** (validation / error text
on a field), **help_text** (tooltip), and **accelerator_key** (drive it via a
hotkey instead of a click). ``ax_props`` exposes those high-value UIA properties.

Each function is a thin dispatch onto the injectable
``accessibility.backends.get_backend()`` seam, so the headless core is
unit-testable on any platform by injecting a fake backend; the real UIA property
reads live in the Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional


def get_element_properties(name: Optional[str] = None, role: Optional[str] = None,
                           app_name: Optional[str] = None,
                           automation_id: Optional[str] = None,
                           ) -> Optional[Dict[str, Any]]:
    """Return ``{enabled, offscreen, help_text, item_status, accelerator_key,
    access_key, orientation}`` for the matched control, or None if not found."""
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend().get_properties(name=name, role=role, app_name=app_name,
                                        automation_id=automation_id)


def is_element_enabled(name: Optional[str] = None, role: Optional[str] = None,
                       app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> Optional[bool]:
    """Return whether the matched control is enabled (None if not found).

    The common guard before acting — don't click a disabled button.
    """
    properties = get_element_properties(name=name, role=role, app_name=app_name,
                                        automation_id=automation_id)
    return properties.get("enabled") if properties else None
