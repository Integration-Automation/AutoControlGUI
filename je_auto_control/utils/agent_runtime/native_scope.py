"""Scope native window and control targets before their existing backend performs an action."""
from __future__ import annotations

import sys
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
def control_owner_scope(process_id: int) -> Iterator[None]:
    """Bound UIA pattern lookup in a serial helper to the verified foreground process."""
    if sys.platform != "win32":
        yield
        return
    from je_auto_control.utils.accessibility.backends import get_backend
    backend: Any = get_backend()
    original = backend._find_raw

    def scoped(*args: Any, **kwargs: Any) -> Any:
        raw = original(*args, **kwargs)
        if raw is not None and int(raw.CurrentProcessId) != process_id:
            raise AgentTaskError("native control belongs to another process")
        return raw

    backend._find_raw = scoped
    try:
        yield
    finally:
        backend._find_raw = original
