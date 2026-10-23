"""Explicit target adapters; native imports occur only during requested operations."""
from __future__ import annotations

import base64
import io
import os
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec

# Only these reviewed commands can drive the default desktop adapter. Additional
# application integrations register their own adapter instead of receiving all AC_*.
DESKTOP_TOOLS = frozenset({
    "AC_click_mouse", "AC_set_mouse_position", "AC_mouse_scroll", "AC_write", "AC_hotkey",
    "AC_press_keyboard_key", "AC_release_keyboard_key", "AC_press_mouse", "AC_release_mouse",
    "AC_control_get_value", "AC_control_get_state", "AC_control_set_value", "AC_control_invoke",
    "AC_control_toggle", "AC_handle_file_dialog", "AC_list_windows", "AC_focus_window",
    "AC_click_text", "AC_find_text", "AC_snap_window", "AC_read_workbook", "AC_read_document",
    "AC_extract_pdf_text", "AC_get_clipboard", "AC_set_clipboard",
})


class DesktopTarget:
    """An explicit foreground-application scope over the existing native wrappers."""

    def __init__(self) -> None:
        self._spec: AgentTaskSpec | None = None
        self._owned_keys: set[str] = set()
        self._owned_buttons: set[str] = set()

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Check interactive-session and application scope without claiming permissions."""
        from je_auto_control.utils.session_guard import ensure_interactive_session
        ensure_interactive_session()
        if not spec.apps:
            return False, "desktop tasks require explicit allowed application names"
        if not set(spec.allowed_tools) <= DESKTOP_TOOLS:
            return False, "one or more tools lack a reviewed desktop adapter"
        self._spec = spec
        self._check_foreground()
        return True, ""

    def _check_foreground(self) -> tuple[int, str, int]:
        from je_auto_control.wrapper.auto_control_window import foreground_window, foreground_window_process_id
        from je_auto_control.utils.accessibility.accessibility_api import list_accessibility_elements
        window = foreground_window()
        process_id = foreground_window_process_id()
        if not window or not process_id or self._spec is None:
            raise AgentTaskError("foreground target cannot be identified")
        elements = list_accessibility_elements(max_results=20, window_title=window[1])
        names = {item.app_name.casefold() for item in elements if item.process_id == process_id and item.app_name}
        names.update(os.path.basename(name) for name in tuple(names))
        if not names.intersection(name.casefold() for name in self._spec.apps):
            raise AgentTaskError("foreground application is outside the task scope")
        return int(window[0]), window[1], int(process_id)

    def observe(self) -> dict[str, Any]:
        """Observe bounded scoped controls; optional images stay in the observation's memory only."""
        from je_auto_control.utils.accessibility.accessibility_api import list_accessibility_elements
        hwnd, title, pid = self._check_foreground()
        controls = list_accessibility_elements(max_results=200, window_title=title)
        elements: list[dict[str, Any]] = []
        for item in controls:
            if item.process_id != pid:
                continue
            data = item.to_dict()
            sensitive = any(word in str(item.role).lower() for word in ("password", "edit", "textbox", "50004"))
            if sensitive:
                data["name"] = "[redacted]"
            data["is_password"] = sensitive
            data["index"] = len(elements)
            elements.append(data)
        result = {"identity": {"window": hwnd, "process": pid, "title": title}, "elements": elements}
        if self._spec is not None and self._spec.options.get("vision"):
            result["image"] = self._image(hwnd, elements)
        return result

    @staticmethod
    def _image(hwnd: int, elements: list[dict]) -> dict[str, Any]:
        image, origin = _window_frame(hwnd)
        original = image.size
        redacted = _redact_frame(image, elements, origin)
        redacted.thumbnail((1280, 1280))
        buffer = io.BytesIO()
        redacted.convert("RGB").save(buffer, format="JPEG", quality=65)
        return {"format": "jpeg", "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
                "origin": list(origin), "original_size": list(original), "image_size": list(redacted.size)}

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute reviewed commands, with a final foreground check immediately before dispatch."""
        from je_auto_control.utils.tool_use_schema import run_tool_call
        if name not in DESKTOP_TOOLS:
            raise AgentTaskError("tool lacks a reviewed desktop adapter")
        self._check_foreground()
        self._track(name, arguments)
        result = run_tool_call(name, arguments)
        self._released(name, arguments)
        return result

    def _track(self, name: str, arguments: dict[str, Any]) -> None:
        if name == "AC_press_keyboard_key":
            self._owned_keys.add(str(arguments.get("keycode", "")))
        elif name == "AC_press_mouse":
            self._owned_buttons.add(str(arguments.get("mouse_keycode", "mouse_left")))

    def _released(self, name: str, arguments: dict[str, Any]) -> None:
        if name == "AC_release_keyboard_key":
            self._owned_keys.discard(str(arguments.get("keycode", "")))
        elif name == "AC_release_mouse":
            self._owned_buttons.discard(str(arguments.get("mouse_keycode", "mouse_left")))

    def cleanup(self) -> None:
        """Release only keys/buttons explicitly held by this adapter's current task."""
        from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key
        from je_auto_control.wrapper.auto_control_mouse import release_mouse
        for key in tuple(self._owned_keys):
            release_keyboard_key(key)
            self._owned_keys.discard(key)
        for button in tuple(self._owned_buttons):
            release_mouse(button)
            self._owned_buttons.discard(button)
        self._spec = None


def _window_frame(hwnd: int) -> tuple[Any, tuple[int, int]]:
    if os.name != "nt":
        raise AgentTaskError("window-scoped vision capture has not been configured on this platform")
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    from je_auto_control.utils.window_capture.window_capture import _win32_geometry
    geometry = _win32_geometry(hwnd)
    if geometry is None:
        raise AgentTaskError("window-scoped vision geometry is unavailable")
    x, y, width, height = geometry
    return pil_screenshot(screen_region=[x, y, x + width, y + height]), (x, y)


def _redact_frame(image: Any, elements: list[dict], origin: tuple[int, int]) -> Any:
    from je_auto_control.utils.redaction.engine import RedactionEngine
    from je_auto_control.utils.redaction.policies import POLICY_STRICT
    x, y = origin
    nodes = [{**item, "bbox": [item["bounds"][0] - x, item["bounds"][1] - y,
                               item["bounds"][0] + item["bounds"][2] - x,
                               item["bounds"][1] + item["bounds"][3] - y]} for item in elements]
    redacted, _report = RedactionEngine(POLICY_STRICT).redact_image(image, {"accessibility": nodes})
    return redacted
