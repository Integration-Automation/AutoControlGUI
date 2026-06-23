"""Window z-order control — always-on-top / topmost, bring-to-front, send-to-back.

``windows_window_manage.set_window_position(hwnd, position)`` exists at the raw Win32
layer but is **not** exported in the package facade, has no title-based wrapper, and no
topmost / not-topmost semantics — and there is no ``always_on_top`` anywhere outside
GUI overlay code. This adds the standard RPA z-order primitive: a pure ``plan_zorder``
that maps an action to the ``SetWindowPos`` insert-after constant, plus title-based
``set_topmost`` / ``bring_to_front`` / ``send_to_back`` over an injectable driver (the
same seam pattern as ``snap_window``).

The planning is pure and headless-testable; only the default driver touches Win32
(returning ``False`` on other platforms). Imports no ``PySide6``.
"""
import sys
from typing import Any, Callable, Dict

ZOrderDriver = Callable[[str, str], bool]

# action -> SetWindowPos hwndInsertAfter constant
_ACTIONS = {"top": 0, "bottom": 1, "topmost": -1, "notopmost": -2}


def available_actions() -> list:
    """Return the supported z-order action names."""
    return list(_ACTIONS)


def plan_zorder(action: str) -> Dict[str, Any]:
    """Return the ``SetWindowPos`` descriptor for a z-order ``action``.

    ``action`` is one of ``top`` / ``bottom`` / ``topmost`` / ``notopmost``; the
    result carries the ``insert_after`` HWND constant and the move/size-preserving
    flags. Raises ``ValueError`` for an unknown action.
    """
    if action not in _ACTIONS:
        raise ValueError(f"unknown z-order action: {action!r}")
    return {"action": action, "insert_after": _ACTIONS[action],
            "flags": ["SWP_NOMOVE", "SWP_NOSIZE"]}


def _default_driver(title: str, action: str) -> bool:
    """Apply a z-order action to the window matching ``title`` (Win32 only)."""
    if not sys.platform.startswith("win"):
        return False
    from je_auto_control.wrapper.auto_control_window import find_window
    hit = find_window(title)
    if hit is None:
        return False
    from je_auto_control.windows.window import windows_window_manage as wm
    wm.set_window_position(int(hit[0]), plan_zorder(action)["insert_after"])
    return True


def set_topmost(title: str, on: bool = True, *,
                driver: Callable[[str, str], bool] = None) -> bool:
    """Pin the window matching ``title`` always-on-top (or release it when ``on`` is False)."""
    return (driver or _default_driver)(title, "topmost" if on else "notopmost")


def bring_to_front(title: str, *,
                   driver: Callable[[str, str], bool] = None) -> bool:
    """Raise the window matching ``title`` to the top of the z-order."""
    return (driver or _default_driver)(title, "top")


def send_to_back(title: str, *,
                 driver: Callable[[str, str], bool] = None) -> bool:
    """Send the window matching ``title`` to the bottom of the z-order."""
    return (driver or _default_driver)(title, "bottom")
