"""Explicit target adapters; native imports occur only during requested operations."""
from __future__ import annotations

import base64
import io
import os
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.workspace_scope import bootstrap_allowed, focus_approved

# Only these reviewed commands can drive the default desktop adapter. Additional
# application integrations register their own adapter instead of receiving all AC_*.
DESKTOP_TOOLS = frozenset({
    "AC_click_mouse", "AC_set_mouse_position", "AC_mouse_scroll", "AC_write", "AC_hotkey",
    "AC_press_keyboard_key", "AC_release_keyboard_key", "AC_press_mouse", "AC_release_mouse",
    "AC_control_get_value", "AC_control_get_state", "AC_control_set_value", "AC_control_invoke",
    "AC_control_toggle", "AC_handle_file_dialog", "AC_list_windows", "AC_focus_window",
    "AC_click_text", "AC_find_text", "AC_snap_window", "AC_read_workbook", "AC_read_document",
    "AC_extract_pdf_text", "AC_get_clipboard", "AC_set_clipboard",
    "AC_workflow_control", "AC_workflow_open", "AC_workflow_wait",
})


class DesktopTarget:
    """An explicit foreground-application scope over the existing native wrappers."""

    def __init__(self) -> None:
        self._spec: AgentTaskSpec | None = None
        self._action_identity: tuple[int, int] | None = None
        self._app_name = ""

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Check interactive-session and application scope without claiming permissions."""
        from je_auto_control.utils.session_guard import ensure_interactive_session
        ensure_interactive_session()
        if not spec.apps:
            return False, "desktop tasks require explicit allowed application names"
        if not set(spec.allowed_tools) <= DESKTOP_TOOLS:
            return False, "one or more tools lack a reviewed desktop adapter"
        self._spec = spec
        if not bootstrap_allowed(spec):
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
        self._app_name = _application_name(elements, process_id, self._spec.apps)
        return int(window[0]), window[1], int(process_id)

    def observe(self) -> dict[str, Any]:
        """Observe bounded scoped controls; optional images stay in the observation's memory only."""
        from je_auto_control.utils.accessibility.accessibility_api import list_accessibility_elements
        try:
            hwnd, title, pid = self._check_foreground()
        except AgentTaskError:
            if bootstrap_allowed(self._spec):
                return {"identity": "approved-window-bootstrap", "elements": [], "state": "waiting_for_window"}
            raise
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
        current_hwnd, _current_title, current_pid = self._check_foreground()
        if (current_hwnd, current_pid) != (hwnd, pid):
            raise AgentTaskError("foreground target changed during observation")
        return result

    @staticmethod
    def _image(hwnd: int, elements: list[dict]) -> dict[str, Any]:
        image, origin = _window_frame(hwnd)
        original = image.size
        redacted = _redact_frame(image, elements, origin)
        redacted.thumbnail((1280, 1280))
        buffer = io.BytesIO()
        redacted.convert("RGB").save(buffer, format="JPEG", quality=65)
        return {"format": "jpeg", "redacted_by": "strict", "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
                "origin": list(origin), "original_size": list(original), "image_size": list(redacted.size),
                "coordinate_space": "desktop"}

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute reviewed commands, with a final foreground check immediately before dispatch."""
        from je_auto_control.utils.tool_use_schema import run_tool_call
        if name not in DESKTOP_TOOLS:
            raise AgentTaskError("tool lacks a reviewed desktop adapter")
        if name == "AC_workflow_open":
            raise AgentTaskError("approved document launch must be owned by the host outside its input helper")
        if name == "AC_focus_window" and bootstrap_allowed(self._spec):
            return focus_approved(self._spec, arguments)
        hwnd, _title, pid = self._check_foreground()
        self._action_identity = hwnd, pid
        if name.startswith("AC_control_"):
            if arguments.get("app_name", self._app_name).casefold() != self._app_name.casefold():
                raise AgentTaskError("control application is outside the current target")
            arguments = {**arguments, "app_name": self._app_name}
        from je_auto_control.utils.agent_runtime.native_scope import control_owner_scope, check_window_arguments
        check_window_arguments(arguments, self._spec)
        with control_owner_scope(pid):
            return run_tool_call(name, arguments)

    def validate_input(self, event: dict) -> None:
        """Refuse new input after focus changes or a point leaves the authorized window."""
        if event["kind"] in {"key_release", "key_released", "mouse_release", "mouse_released"}:
            return
        hwnd, _title, pid = self._check_foreground()
        if self._action_identity is not None and self._action_identity != (hwnd, pid):
            raise AgentTaskError("foreground target changed during native input")
        if event["kind"] == "scroll":
            from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
            point = get_mouse_position()
            if point is None:
                raise AgentTaskError("scroll target cannot be identified")
            event = {**event, "x": point[0], "y": point[1]}
        if event["kind"] in {"pointer", "mouse_press", "scroll"}:
            from je_auto_control.utils.agent_runtime.native_scope import check_pointer
            check_pointer(hwnd, event)

    def prepare_input(self, event: dict) -> None:
        """Position and confirm the actual pointer before acknowledging an owned button press."""
        from je_auto_control.wrapper.auto_control_mouse import set_mouse_position, get_mouse_position
        point = event["x"], event["y"]
        set_mouse_position(*point)
        if get_mouse_position() != point:
            raise AgentTaskError("native pointer position was not confirmed before pressing")

    def cleanup(self) -> None:
        """Retire helper-local scope; the host ledger owns every key/button release."""
        self._spec = None
        self._action_identity = None


def _application_name(elements: list[Any], process_id: int, apps: tuple[str, ...]) -> str:
    names = [item.app_name for item in elements if item.process_id == process_id and item.app_name]
    allowed = {name.casefold() for name in apps}
    for name in names:
        if {name.casefold(), os.path.basename(name).casefold()} & allowed:
            return name
    raise AgentTaskError("foreground application is outside the task scope")


def _window_frame(hwnd: int) -> tuple[Any, tuple[int, int]]:
    from je_auto_control.utils.agent_runtime.window_pixels import capture_window
    return capture_window(hwnd)


def _redact_frame(image: Any, elements: list[dict], origin: tuple[int, int]) -> Any:
    from je_auto_control.utils.redaction.engine import RedactionEngine
    from je_auto_control.utils.redaction.policies import POLICY_STRICT
    x, y = origin
    nodes = [{**item, "bbox": [item["bounds"][0] - x, item["bounds"][1] - y,
                               item["bounds"][0] + item["bounds"][2] - x,
                               item["bounds"][1] + item["bounds"][3] - y]} for item in elements]
    redacted, _report = RedactionEngine(POLICY_STRICT).redact_image(image, {"accessibility": nodes})
    return redacted
