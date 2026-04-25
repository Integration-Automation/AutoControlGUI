"""MCP tool registry and adapters backed by AutoControl's headless API.

Each :class:`MCPTool` pairs a public name with a JSON Schema (which the
MCP client surfaces to the model) and a Python callable. Adapters in
this module keep return values JSON-friendly (lists / dicts / strings)
so they survive the JSON-RPC boundary, and translate user-facing
parameter shapes into the underlying AutoControl signatures.

All wrapper imports are lazy so importing this module — and therefore
booting the MCP server — does not pull in heavy backends (cv2, OCR,
Win32) until a tool is actually called.
"""
import base64
import io
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class MCPContent:
    """One content block returned to an MCP client.

    The ``type`` field follows the MCP content discriminator: ``text``,
    ``image``, or ``resource``. Tools normally return plain Python
    objects (auto-wrapped in a single ``text`` block); use this class
    when a tool needs to return non-text content such as a screenshot.
    """

    type: str
    text: Optional[str] = None
    data: Optional[str] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON shape MCP clients expect for one content block."""
        if self.type == "text":
            return {"type": "text", "text": self.text or ""}
        if self.type == "image":
            return {
                "type": "image", "data": self.data or "",
                "mimeType": self.mime_type or "image/png",
            }
        return {"type": self.type, "text": self.text or ""}

    @classmethod
    def text_block(cls, text: str) -> "MCPContent":
        return cls(type="text", text=text)

    @classmethod
    def image_block(cls, data: str,
                    mime_type: str = "image/png") -> "MCPContent":
        return cls(type="image", data=data, mime_type=mime_type)


@dataclass(frozen=True)
class MCPToolAnnotations:
    """MCP behaviour hints surfaced to the client per the 2025-03-26 spec.

    Defaults follow the spec: a tool is assumed to mutate state in an
    open world unless it explicitly opts in to read-only / closed-world.
    These hints are advisory — clients may use them to require user
    confirmation before destructive calls but MUST NOT rely on them for
    security.
    """

    title: Optional[str] = None
    read_only: bool = False
    destructive: bool = True
    idempotent: bool = False
    open_world: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON shape MCP clients expect under ``annotations``."""
        annotations: Dict[str, Any] = {
            "readOnlyHint": self.read_only,
            "destructiveHint": False if self.read_only else self.destructive,
            "idempotentHint": self.idempotent,
            "openWorldHint": self.open_world,
        }
        if self.title is not None:
            annotations["title"] = self.title
        return annotations


@dataclass(frozen=True)
class MCPTool:
    """A single MCP tool — public name, schema, and Python callable."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]
    annotations: MCPToolAnnotations = MCPToolAnnotations()

    def to_descriptor(self) -> Dict[str, Any]:
        """Return the dict shape MCP clients expect from ``tools/list``."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": self.annotations.to_dict(),
        }

    def invoke(self, arguments: Dict[str, Any]) -> Any:
        """Call the underlying handler with keyword arguments."""
        return self.handler(**arguments)


def _schema(properties: Dict[str, Any],
            required: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build a JSON Schema object node from a property mapping."""
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return schema


# === Adapter helpers ========================================================

def _click_mouse(mouse_keycode: str = "mouse_left",
                 x: Optional[int] = None,
                 y: Optional[int] = None) -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import click_mouse
    keycode, click_x, click_y = click_mouse(mouse_keycode, x, y)
    return [int(keycode), int(click_x), int(click_y)]


def _set_mouse_position(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
    moved = set_mouse_position(int(x), int(y))
    return [int(moved[0]), int(moved[1])]


def _get_mouse_position() -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
    pos = get_mouse_position()
    return [] if pos is None else [int(pos[0]), int(pos[1])]


def _mouse_scroll(scroll_value: int,
                  x: Optional[int] = None,
                  y: Optional[int] = None,
                  scroll_direction: str = "scroll_down") -> List[Any]:
    from je_auto_control.wrapper.auto_control_mouse import mouse_scroll
    value, direction = mouse_scroll(int(scroll_value), x, y, scroll_direction)
    return [int(value), str(direction)]


def _type_text(text: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import write
    return write(text) or ""


def _press_key(keycode: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
    return type_keyboard(keycode) or ""


def _hotkey(keys: List[str]) -> List[str]:
    from je_auto_control.wrapper.auto_control_keyboard import hotkey
    pressed, released = hotkey(list(keys))
    return [pressed, released]


def _screen_size() -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import screen_size
    width, height = screen_size()
    return [int(width), int(height)]


def _screenshot(file_path: Optional[str] = None,
                screen_region: Optional[List[int]] = None
                ) -> List[MCPContent]:
    """Take a screenshot, optionally save it, and return image + path.

    The result always includes a base64 PNG content block so MCP
    clients can show the screen to the model. If ``file_path`` is
    given, the screenshot is also saved there and a text block with
    the resolved absolute path is appended.
    """
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    saved_path: Optional[str] = None
    if file_path is not None:
        saved_path = os.path.realpath(os.fspath(file_path))
        parent = os.path.dirname(saved_path) or "."
        if not os.path.isdir(parent):
            raise ValueError(f"screenshot directory does not exist: {parent}")
    image = pil_screenshot(file_path=saved_path, screen_region=screen_region)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    contents: List[MCPContent] = [MCPContent.image_block(encoded)]
    if saved_path is not None:
        contents.append(MCPContent.text_block(f"saved: {saved_path}"))
    return contents


def _get_pixel(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import get_pixel
    pixel = get_pixel(int(x), int(y))
    if pixel is None:
        return []
    return [int(component) for component in pixel]


def _locate_image_center(image_path: str,
                         detect_threshold: float = 1.0) -> List[int]:
    from je_auto_control.wrapper.auto_control_image import locate_image_center
    cx, cy = locate_image_center(image_path,
                                 detect_threshold=float(detect_threshold))
    return [int(cx), int(cy)]


def _locate_and_click(image_path: str,
                      mouse_keycode: str = "mouse_left",
                      detect_threshold: float = 1.0) -> List[int]:
    from je_auto_control.wrapper.auto_control_image import locate_and_click
    cx, cy = locate_and_click(image_path, mouse_keycode,
                              detect_threshold=float(detect_threshold))
    return [int(cx), int(cy)]


def _locate_text(text: str,
                 region: Optional[List[int]] = None,
                 min_confidence: float = 60.0) -> List[int]:
    from je_auto_control.utils.ocr.ocr_engine import locate_text_center
    cx, cy = locate_text_center(text, region=region,
                                min_confidence=float(min_confidence))
    return [int(cx), int(cy)]


def _click_text(text: str,
                mouse_keycode: str = "mouse_left",
                region: Optional[List[int]] = None,
                min_confidence: float = 60.0) -> List[int]:
    from je_auto_control.utils.ocr.ocr_engine import click_text
    cx, cy = click_text(text, mouse_keycode=mouse_keycode, region=region,
                        min_confidence=float(min_confidence))
    return [int(cx), int(cy)]


def _list_windows() -> List[Dict[str, Any]]:
    from je_auto_control.wrapper.auto_control_window import list_windows
    return [{"hwnd": int(hwnd), "title": title}
            for hwnd, title in list_windows()]


def _focus_window(title_substring: str,
                  case_sensitive: bool = False) -> int:
    from je_auto_control.wrapper.auto_control_window import focus_window
    return int(focus_window(title_substring, case_sensitive=case_sensitive))


def _wait_for_window(title_substring: str,
                     timeout: float = 10.0,
                     case_sensitive: bool = False) -> int:
    from je_auto_control.wrapper.auto_control_window import wait_for_window
    return int(wait_for_window(title_substring, timeout=float(timeout),
                               case_sensitive=case_sensitive))


def _close_window(title_substring: str,
                  case_sensitive: bool = False) -> bool:
    from je_auto_control.wrapper.auto_control_window import close_window_by_title
    return bool(close_window_by_title(title_substring,
                                       case_sensitive=case_sensitive))


def _get_clipboard() -> str:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard
    return get_clipboard()


def _set_clipboard(text: str) -> str:
    from je_auto_control.utils.clipboard.clipboard import set_clipboard
    set_clipboard(text)
    return "ok"


def _execute_actions(actions: List[Any]) -> Dict[str, str]:
    from je_auto_control.utils.executor.action_executor import execute_action
    result = execute_action(actions)
    return {key: str(value) for key, value in result.items()}


def _execute_action_file(file_path: str) -> Dict[str, str]:
    from je_auto_control.utils.executor.action_executor import execute_action
    from je_auto_control.utils.json.json_file import read_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    result = execute_action(read_action_json(safe_path))
    return {key: str(value) for key, value in result.items()}


def _list_run_history(limit: int = 50,
                      source_type: Optional[str] = None) -> List[Dict[str, Any]]:
    from je_auto_control.utils.run_history.history_store import default_history_store
    rows = default_history_store.list_runs(limit=int(limit),
                                            source_type=source_type)
    return [{
        "id": row.id, "source_type": row.source_type,
        "source_id": row.source_id, "script_path": row.script_path,
        "started_at": str(row.started_at),
        "finished_at": str(row.finished_at),
        "status": row.status, "error_text": row.error_text,
        "duration_seconds": row.duration_seconds,
    } for row in rows]


def _list_action_commands() -> List[str]:
    from je_auto_control.utils.executor.action_executor import executor
    return sorted(executor.known_commands())


def _record_start() -> str:
    from je_auto_control.wrapper.auto_control_record import record
    record()
    return "recording started"


def _record_stop() -> List[Any]:
    from je_auto_control.wrapper.auto_control_record import stop_record
    return stop_record() or []


def _read_action_file(file_path: str) -> List[Any]:
    from je_auto_control.utils.json.json_file import read_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    return read_action_json(safe_path)


def _write_action_file(file_path: str, actions: List[Any]) -> str:
    from je_auto_control.utils.json.json_file import write_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    parent = os.path.dirname(safe_path) or "."
    if not os.path.isdir(parent):
        raise ValueError(f"action-file directory does not exist: {parent}")
    write_action_json(safe_path, actions)
    return safe_path


def _trim_actions(actions: List[Any], start: int = 0,
                  end: Optional[int] = None) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import trim_actions
    return trim_actions(actions, start=int(start),
                        end=None if end is None else int(end))


def _adjust_delays(actions: List[Any], factor: float = 1.0,
                   clamp_ms: int = 0) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import adjust_delays
    return adjust_delays(actions, factor=float(factor),
                         clamp_ms=int(clamp_ms))


def _scale_coordinates(actions: List[Any], x_factor: float = 1.0,
                       y_factor: float = 1.0) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import scale_coordinates
    return scale_coordinates(actions, x_factor=float(x_factor),
                             y_factor=float(y_factor))


# === Tool builders ==========================================================

_DESTRUCTIVE = MCPToolAnnotations(destructive=True)
_NON_DESTRUCTIVE = MCPToolAnnotations(destructive=False, idempotent=True)
_READ_ONLY = MCPToolAnnotations(read_only=True, idempotent=True)


def _mouse_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_click_mouse",
            description=("Click a mouse button at (x, y). "
                         "mouse_keycode: mouse_left, mouse_right, mouse_middle. "
                         "If x/y are omitted, clicks at the current cursor."),
            input_schema=_schema({
                "mouse_keycode": {"type": "string",
                                   "description": "mouse_left | mouse_right | mouse_middle"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }),
            handler=_click_mouse,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_get_mouse_position",
            description="Return the current cursor position as [x, y].",
            input_schema=_schema({}),
            handler=_get_mouse_position,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_set_mouse_position",
            description="Move the cursor to absolute screen coordinates (x, y).",
            input_schema=_schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["x", "y"]),
            handler=_set_mouse_position,
            annotations=_NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_mouse_scroll",
            description=("Scroll the mouse wheel by scroll_value units. "
                         "scroll_direction is Linux-only: scroll_up | scroll_down."),
            input_schema=_schema({
                "scroll_value": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "scroll_direction": {"type": "string"},
            }, required=["scroll_value"]),
            handler=_mouse_scroll,
            annotations=_DESTRUCTIVE,
        ),
    ]


def _keyboard_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_type_text",
            description=("Type a string by pressing each character. "
                         "Use ac_press_key or ac_hotkey for control keys."),
            input_schema=_schema({"text": {"type": "string"}},
                                 required=["text"]),
            handler=_type_text,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_press_key",
            description=("Press and release one keyboard key. keycode is a "
                         "name from get_keyboard_keys_table (e.g. enter, tab, "
                         "f1, a, 1)."),
            input_schema=_schema({"keycode": {"type": "string"}},
                                 required=["keycode"]),
            handler=_press_key,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_hotkey",
            description=("Press a key combination, e.g. ['ctrl', 'c']. "
                         "Keys are pressed in order then released in reverse."),
            input_schema=_schema({
                "keys": {"type": "array", "items": {"type": "string"}},
            }, required=["keys"]),
            handler=_hotkey,
            annotations=_DESTRUCTIVE,
        ),
    ]


def _screen_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_screen_size",
            description="Return the primary screen size as [width, height].",
            input_schema=_schema({}),
            handler=_screen_size,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_screenshot",
            description=("Take a screenshot and return it as a base64 PNG "
                         "image content block so the model can see the "
                         "screen. If file_path is provided, the image is "
                         "also saved there. screen_region is "
                         "[x, y, width, height]."),
            input_schema=_schema({
                "file_path": {"type": "string"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
            }),
            handler=_screenshot,
            annotations=MCPToolAnnotations(destructive=False, idempotent=False),
        ),
        MCPTool(
            name="ac_get_pixel",
            description="Return the pixel colour at (x, y) as a list of channels.",
            input_schema=_schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["x", "y"]),
            handler=_get_pixel,
            annotations=_READ_ONLY,
        ),
    ]


def _image_and_ocr_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_locate_image_center",
            description=("Find a template image on screen and return its "
                         "centre [x, y]. detect_threshold is 0.0–1.0."),
            input_schema=_schema({
                "image_path": {"type": "string"},
                "detect_threshold": {"type": "number"},
            }, required=["image_path"]),
            handler=_locate_image_center,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_locate_and_click",
            description="Find a template image and click its centre.",
            input_schema=_schema({
                "image_path": {"type": "string"},
                "mouse_keycode": {"type": "string"},
                "detect_threshold": {"type": "number"},
            }, required=["image_path"]),
            handler=_locate_and_click,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_locate_text",
            description=("OCR the screen for ``text`` and return the centre "
                         "[x, y] of the first match. region is "
                         "[x, y, width, height]. Requires Tesseract."),
            input_schema=_schema({
                "text": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "min_confidence": {"type": "number"},
            }, required=["text"]),
            handler=_locate_text,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_click_text",
            description="OCR for ``text`` and click its centre.",
            input_schema=_schema({
                "text": {"type": "string"},
                "mouse_keycode": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "min_confidence": {"type": "number"},
            }, required=["text"]),
            handler=_click_text,
            annotations=_DESTRUCTIVE,
        ),
    ]


def _window_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_list_windows",
            description=("List visible top-level windows as "
                         "[{hwnd, title}, ...] (Windows only)."),
            input_schema=_schema({}),
            handler=_list_windows,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_focus_window",
            description="Bring the first window matching title_substring to the front.",
            input_schema=_schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=_focus_window,
            annotations=_NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_wait_for_window",
            description="Poll until a window with title_substring exists; return its hwnd.",
            input_schema=_schema({
                "title_substring": {"type": "string"},
                "timeout": {"type": "number"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=_wait_for_window,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_close_window",
            description="Minimise the first window matching title_substring.",
            input_schema=_schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=_close_window,
            annotations=_DESTRUCTIVE,
        ),
    ]


def _system_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_get_clipboard",
            description="Return the current text clipboard contents.",
            input_schema=_schema({}),
            handler=_get_clipboard,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_set_clipboard",
            description="Replace the text clipboard contents with ``text``.",
            input_schema=_schema({"text": {"type": "string"}},
                                 required=["text"]),
            handler=_set_clipboard,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_execute_actions",
            description=("Run a list of AutoControl actions through the "
                         "executor. Each action is [name, args] where name "
                         "starts with AC_ (see ac_list_action_commands)."),
            input_schema=_schema({
                "actions": {"type": "array",
                            "items": {"type": "array"}},
            }, required=["actions"]),
            handler=_execute_actions,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_execute_action_file",
            description="Load a JSON action file from disk and execute it.",
            input_schema=_schema({"file_path": {"type": "string"}},
                                 required=["file_path"]),
            handler=_execute_action_file,
            annotations=_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_list_action_commands",
            description="Return every action command name the executor recognises.",
            input_schema=_schema({}),
            handler=_list_action_commands,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_list_run_history",
            description=("Return recent script-run history records "
                         "(id, status, source_type, started_at, ...)."),
            input_schema=_schema({
                "limit": {"type": "integer"},
                "source_type": {"type": "string"},
            }),
            handler=_list_run_history,
            annotations=_READ_ONLY,
        ),
    ]


def _read_only_env_flag() -> bool:
    """Return True when JE_AUTOCONTROL_MCP_READONLY is set to a truthy value."""
    raw = os.environ.get("JE_AUTOCONTROL_MCP_READONLY", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _recording_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_record_start",
            description=("Start recording mouse and keyboard events in the "
                         "background. Call ac_record_stop to retrieve the "
                         "captured action list. Not supported on macOS."),
            input_schema=_schema({}),
            handler=_record_start,
            annotations=MCPToolAnnotations(destructive=False, idempotent=False),
        ),
        MCPTool(
            name="ac_record_stop",
            description=("Stop the active recorder and return the captured "
                         "action list ([[command, args], ...]) ready to "
                         "feed back into ac_execute_actions."),
            input_schema=_schema({}),
            handler=_record_stop,
            annotations=MCPToolAnnotations(destructive=False, idempotent=False),
        ),
        MCPTool(
            name="ac_read_action_file",
            description="Read a JSON action file from disk and return its parsed contents.",
            input_schema=_schema({"file_path": {"type": "string"}},
                                 required=["file_path"]),
            handler=_read_action_file,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_write_action_file",
            description="Persist an action list to a JSON file at file_path.",
            input_schema=_schema({
                "file_path": {"type": "string"},
                "actions": {"type": "array"},
            }, required=["file_path", "actions"]),
            handler=_write_action_file,
            annotations=MCPToolAnnotations(destructive=False, idempotent=False),
        ),
        MCPTool(
            name="ac_trim_actions",
            description=("Return actions[start:end] as a new list — useful "
                         "for cleaning up the head/tail of a recording."),
            input_schema=_schema({
                "actions": {"type": "array"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            }, required=["actions"]),
            handler=_trim_actions,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_adjust_delays",
            description=("Scale every AC_sleep delay by ``factor`` and "
                         "optionally clamp to a minimum of clamp_ms."),
            input_schema=_schema({
                "actions": {"type": "array"},
                "factor": {"type": "number"},
                "clamp_ms": {"type": "integer"},
            }, required=["actions"]),
            handler=_adjust_delays,
            annotations=_READ_ONLY,
        ),
        MCPTool(
            name="ac_scale_coordinates",
            description=("Scale every x/y coordinate in an action list — "
                         "useful when replaying a recording on a different "
                         "resolution."),
            input_schema=_schema({
                "actions": {"type": "array"},
                "x_factor": {"type": "number"},
                "y_factor": {"type": "number"},
            }, required=["actions"]),
            handler=_scale_coordinates,
            annotations=_READ_ONLY,
        ),
    ]


def build_default_tool_registry(read_only: Optional[bool] = None
                                ) -> List[MCPTool]:
    """Return the full set of tools the MCP server exposes by default.

    :param read_only: when True, drop every tool whose annotations
        indicate it can mutate state. When None (default), the value
        of ``JE_AUTOCONTROL_MCP_READONLY`` is consulted, so deployments
        can pin the server in safe mode without code changes.
    """
    enforce_read_only = (
        _read_only_env_flag() if read_only is None else bool(read_only)
    )
    tools: List[MCPTool] = []
    for batch in (_mouse_tools, _keyboard_tools, _screen_tools,
                  _image_and_ocr_tools, _window_tools, _system_tools,
                  _recording_tools):
        tools.extend(batch())
    if enforce_read_only:
        tools = [tool for tool in tools if tool.annotations.read_only]
    return tools
