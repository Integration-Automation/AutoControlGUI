"""Reactive UI Automation event waits (focus-changed).

The accessibility recorder *polls* the focused element every ~250 ms, so it can
miss a fast focus transition and reacts a quarter-second late. UIA exposes real
events: ``wait_for_focus_change`` blocks on the native
``AddFocusChangedEventHandler`` and returns the moment focus moves — the
zero-latency, miss-free "wait until focus lands on the dialog" primitive, the
accessibility-tree analogue of ``wait_for_window`` / ``wait_for_image``.

It is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam — headless-testable on any platform by injecting a fake backend; the real
event subscription (registered / unregistered under a lock, on the calling
thread) lives in the Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional


def wait_for_focus_change(*, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Block until the keyboard focus moves, then return the newly-focused element.

    Returns the focused element as ``{name, role, app_name, bounds, ...}``, or
    ``None`` if no focus change occurs within ``timeout`` seconds.
    """
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend().wait_for_focus_change(float(timeout))
