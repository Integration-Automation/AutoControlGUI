"""Scope native window and control targets before their existing backend performs an action."""
from __future__ import annotations

import sys
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec


def check_pointer(hwnd: int, event: dict) -> None:
    """Require coordinates within the actual owned window; no desktop-wide fallback."""
    if sys.platform != "win32":
        raise AgentTaskError("window-scoped pointer geometry needs a platform adapter")
    from je_auto_control.utils.window_capture.window_capture import _win32_geometry
    geometry = _win32_geometry(hwnd)
    if geometry is None:
        raise AgentTaskError("owned window geometry is unavailable")
    x, y, width, height = geometry
    if not x <= event["x"] < x + width or not y <= event["y"] < y + height:
        raise AgentTaskError("pointer is outside the owned window")
    if _point_window(event["x"], event["y"]) != hwnd:
        raise AgentTaskError("pointer target is covered by another window or unavailable")


def _hit_library() -> Any:
    if sys.platform != "win32":
        raise AgentTaskError("window hit testing needs a platform adapter")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.WindowFromPoint.argtypes, user.WindowFromPoint.restype = [wintypes.POINT], wintypes.HWND
    user.GetAncestor.argtypes, user.GetAncestor.restype = [wintypes.HWND, wintypes.UINT], wintypes.HWND
    user.GetForegroundWindow.argtypes, user.GetForegroundWindow.restype = [], wintypes.HWND
    return user


def _point_window(x: int, y: int) -> int | None:
    user = _hit_library()
    hit = user.WindowFromPoint(wintypes.POINT(x, y))
    return int(user.GetAncestor(hit, 2) or 0) if hit else None  # GA_ROOT retains owned child controls.


def check_window_arguments(arguments: dict, spec: AgentTaskSpec | None) -> None:
    """Reject ambiguous or foreign explicit window selections before native dispatch."""
    from je_auto_control.wrapper.auto_control_window import list_windows, window_process_id
    for name in ("title", "title_substring", "window_title"):
        title = arguments.get(name)
        if not isinstance(title, str) or not title:
            continue
        matches = [(handle, text) for handle, text in list_windows() if title.casefold() in text.casefold()]
        if len(matches) != 1 or spec is None:
            raise AgentTaskError("window selection is ambiguous or unavailable")
        process = window_process_id(matches[0][1])
        if not _allowed_process(matches[0][1], process, spec.apps):
            raise AgentTaskError("selected window is outside the application scope")


def _allowed_process(title: str, process: int | None, apps: tuple[str, ...]) -> bool:
    from je_auto_control.utils.accessibility.accessibility_api import list_accessibility_elements
    nodes = list_accessibility_elements(window_title=title, max_results=20)
    allowed = {name.casefold() for name in apps}
    return any(node.process_id == process and node.app_name.casefold() in allowed for node in nodes)


@contextmanager
def control_owner_scope(process_id: int, window_id: int) -> Iterator[None]:
    """Bound UIA pattern lookup in a serial helper to the verified foreground window and process."""
    if sys.platform != "win32":
        yield
        return
    from je_auto_control.utils.accessibility.backends import get_backend
    backend: Any = get_backend()
    original = backend._find_raw
    errors = getattr(sys.modules.get(type(backend).__module__), "_UIA_ERRORS",
                     (OSError, AttributeError, ValueError, TypeError))

    def scoped(*args: Any, **kwargs: Any) -> Any:
        try:
            raw = original(*args, **kwargs)
            if raw is not None:
                _check_control_window(backend, raw, process_id, window_id)
            return raw
        except AgentTaskError:
            raise
        except errors as error:
            raise AgentTaskError("native control window ownership is unavailable") from error

    backend._find_raw = scoped
    try:
        yield
    finally:
        backend._find_raw = original


def _check_control_window(backend: Any, raw: Any, process_id: int, window_id: int) -> None:
    user = _hit_library()
    walker = backend._ensure_automation().ControlViewWalker
    for _depth in range(64):
        if raw is None or not raw:
            break
        if int(raw.CurrentProcessId) != process_id:
            raise AgentTaskError("native control ancestor belongs to another process")
        handle = int(raw.CurrentNativeWindowHandle or 0)
        if handle:
            if user.GetAncestor(handle, 2) != window_id or user.GetForegroundWindow() != window_id:
                raise AgentTaskError("native control belongs to another window or focus changed")
            return
        raw = walker.GetParentElement(raw)
    raise AgentTaskError("native control window ownership could not be proved")
