"""Adapter functions that bridge MCP tool calls to AutoControl's headless API.

Each adapter normalises arguments (parses ints / paths) and return
values (lists / dicts / strings, or :class:`MCPContent`) so they
survive the JSON-RPC boundary. Wrapper imports are lazy to keep the
top-level MCP server boot cheap.
"""
import base64
import io
import os
from typing import Any, Dict, List, Optional

from je_auto_control.utils.mcp_server.tools._base import MCPContent


# === Mouse / keyboard =======================================================

def click_mouse(mouse_keycode: str = "mouse_left",
                x: Optional[int] = None,
                y: Optional[int] = None) -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import click_mouse as _click
    keycode, click_x, click_y = _click(mouse_keycode, x, y)
    return [int(keycode), int(click_x), int(click_y)]


def set_mouse_position(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import set_mouse_position as _move
    moved = _move(int(x), int(y))
    return [int(moved[0]), int(moved[1])]


def get_mouse_position() -> List[int]:
    from je_auto_control.wrapper.auto_control_mouse import get_mouse_position as _pos
    pos = _pos()
    return [] if pos is None else [int(pos[0]), int(pos[1])]


def mouse_scroll(scroll_value: int,
                 x: Optional[int] = None,
                 y: Optional[int] = None,
                 scroll_direction: str = "scroll_down") -> List[Any]:
    from je_auto_control.wrapper.auto_control_mouse import mouse_scroll as _scroll
    value, direction = _scroll(int(scroll_value), x, y, scroll_direction)
    return [int(value), str(direction)]


def type_text(text: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import write
    return write(text) or ""


def press_key(keycode: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
    return type_keyboard(keycode) or ""


def hotkey(keys: List[str]) -> List[str]:
    from je_auto_control.wrapper.auto_control_keyboard import hotkey as _hotkey
    pressed, released = _hotkey(list(keys))
    return [pressed, released]


def drag(start_x: int, start_y: int, end_x: int, end_y: int,
         mouse_keycode: str = "mouse_left") -> List[int]:
    """Drag the cursor from (start_x, start_y) to (end_x, end_y)."""
    from je_auto_control.wrapper.auto_control_mouse import (
        press_mouse, release_mouse, set_mouse_position as _move,
    )
    _move(int(start_x), int(start_y))
    press_mouse(mouse_keycode, int(start_x), int(start_y))
    _move(int(end_x), int(end_y))
    release_mouse(mouse_keycode, int(end_x), int(end_y))
    return [int(end_x), int(end_y)]


def send_key_to_window(window_title: str, keycode: str) -> str:
    from je_auto_control.wrapper.auto_control_keyboard import (
        send_key_event_to_window,
    )
    send_key_event_to_window(window_title, keycode)
    return "ok"


def send_mouse_to_window(window_title: str,
                         mouse_keycode: str = "mouse_left",
                         x: Optional[int] = None,
                         y: Optional[int] = None) -> str:
    from je_auto_control.windows.window import windows_window_manage as wm
    from je_auto_control.wrapper.auto_control_mouse import (
        send_mouse_event_to_window,
    )
    hit = next(((hwnd, title) for hwnd, title in wm.get_all_window_hwnd()
                if window_title.lower() in title.lower()), None)
    if hit is None:
        raise ValueError(f"no window matching {window_title!r}")
    send_mouse_event_to_window(hit[0], mouse_keycode, x=x, y=y)
    return "ok"


# === Screen / image / OCR ===================================================

def screen_size() -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import screen_size as _size
    width, height = _size()
    return [int(width), int(height)]


def screenshot(file_path: Optional[str] = None,
               screen_region: Optional[List[int]] = None
               ) -> List[MCPContent]:
    """Take a screenshot, optionally save it, and return image + path."""
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


def get_pixel(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import get_pixel as _pixel
    pixel = _pixel(int(x), int(y))
    if pixel is None:
        return []
    return [int(component) for component in pixel]


def locate_image_center(image_path: str,
                        detect_threshold: float = 1.0) -> List[int]:
    from je_auto_control.wrapper.auto_control_image import locate_image_center as _loc
    cx, cy = _loc(image_path, detect_threshold=float(detect_threshold))
    return [int(cx), int(cy)]


def locate_and_click(image_path: str,
                     mouse_keycode: str = "mouse_left",
                     detect_threshold: float = 1.0) -> List[int]:
    from je_auto_control.wrapper.auto_control_image import locate_and_click as _loc_click
    cx, cy = _loc_click(image_path, mouse_keycode,
                        detect_threshold=float(detect_threshold))
    return [int(cx), int(cy)]


def locate_text(text: str,
                region: Optional[List[int]] = None,
                min_confidence: float = 60.0) -> List[int]:
    from je_auto_control.utils.ocr.ocr_engine import locate_text_center
    cx, cy = locate_text_center(text, region=region,
                                min_confidence=float(min_confidence))
    return [int(cx), int(cy)]


def click_text(text: str,
               mouse_keycode: str = "mouse_left",
               region: Optional[List[int]] = None,
               min_confidence: float = 60.0) -> List[int]:
    from je_auto_control.utils.ocr.ocr_engine import click_text as _click
    cx, cy = _click(text, mouse_keycode=mouse_keycode, region=region,
                    min_confidence=float(min_confidence))
    return [int(cx), int(cy)]


# === Windows / system =======================================================

def list_windows() -> List[Dict[str, Any]]:
    from je_auto_control.wrapper.auto_control_window import list_windows as _list
    return [{"hwnd": int(hwnd), "title": title}
            for hwnd, title in _list()]


def focus_window(title_substring: str,
                 case_sensitive: bool = False) -> int:
    from je_auto_control.wrapper.auto_control_window import focus_window as _focus
    return int(_focus(title_substring, case_sensitive=case_sensitive))


def wait_for_window(title_substring: str,
                    timeout: float = 10.0,
                    case_sensitive: bool = False) -> int:
    from je_auto_control.wrapper.auto_control_window import wait_for_window as _wait
    return int(_wait(title_substring, timeout=float(timeout),
                     case_sensitive=case_sensitive))


def close_window(title_substring: str,
                 case_sensitive: bool = False) -> bool:
    from je_auto_control.wrapper.auto_control_window import close_window_by_title
    return bool(close_window_by_title(title_substring,
                                       case_sensitive=case_sensitive))


def get_clipboard() -> str:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard as _get
    return _get()


def set_clipboard(text: str) -> str:
    from je_auto_control.utils.clipboard.clipboard import set_clipboard as _set
    _set(text)
    return "ok"


# === Executor / history / recording =========================================

def execute_actions(actions: List[Any]) -> Dict[str, str]:
    from je_auto_control.utils.executor.action_executor import execute_action
    result = execute_action(actions)
    return {key: str(value) for key, value in result.items()}


def execute_action_file(file_path: str) -> Dict[str, str]:
    from je_auto_control.utils.executor.action_executor import execute_action
    from je_auto_control.utils.json.json_file import read_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    result = execute_action(read_action_json(safe_path))
    return {key: str(value) for key, value in result.items()}


def list_action_commands() -> List[str]:
    from je_auto_control.utils.executor.action_executor import executor
    return sorted(executor.known_commands())


def list_run_history(limit: int = 50,
                     source_type: Optional[str] = None
                     ) -> List[Dict[str, Any]]:
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


def record_start() -> str:
    from je_auto_control.wrapper.auto_control_record import record
    record()
    return "recording started"


def record_stop() -> List[Any]:
    from je_auto_control.wrapper.auto_control_record import stop_record
    return stop_record() or []


def read_action_file(file_path: str) -> List[Any]:
    from je_auto_control.utils.json.json_file import read_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    return read_action_json(safe_path)


def write_action_file(file_path: str, actions: List[Any]) -> str:
    from je_auto_control.utils.json.json_file import write_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    parent = os.path.dirname(safe_path) or "."
    if not os.path.isdir(parent):
        raise ValueError(f"action-file directory does not exist: {parent}")
    write_action_json(safe_path, actions)
    return safe_path


def trim_actions(actions: List[Any], start: int = 0,
                 end: Optional[int] = None) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import trim_actions as _trim
    return _trim(actions, start=int(start),
                 end=None if end is None else int(end))


def adjust_delays(actions: List[Any], factor: float = 1.0,
                  clamp_ms: int = 0) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import adjust_delays as _adj
    return _adj(actions, factor=float(factor), clamp_ms=int(clamp_ms))


def scale_coordinates(actions: List[Any], x_factor: float = 1.0,
                      y_factor: float = 1.0) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import scale_coordinates as _scale
    return _scale(actions, x_factor=float(x_factor),
                  y_factor=float(y_factor))


# === Semantic locators (a11y / VLM) =========================================

def a11y_list(app_name: Optional[str] = None,
              max_results: int = 100) -> List[Dict[str, Any]]:
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements,
    )
    return [element.to_dict()
            for element in list_accessibility_elements(
                app_name=app_name, max_results=int(max_results),
            )]


def a11y_find(name: Optional[str] = None,
              role: Optional[str] = None,
              app_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    from je_auto_control.utils.accessibility.accessibility_api import (
        find_accessibility_element,
    )
    element = find_accessibility_element(name=name, role=role,
                                          app_name=app_name)
    return None if element is None else element.to_dict()


def a11y_click(name: Optional[str] = None,
               role: Optional[str] = None,
               app_name: Optional[str] = None) -> bool:
    from je_auto_control.utils.accessibility.accessibility_api import (
        click_accessibility_element,
    )
    return bool(click_accessibility_element(name=name, role=role,
                                             app_name=app_name))


def vlm_locate(description: str,
               screen_region: Optional[List[int]] = None,
               model: Optional[str] = None) -> Optional[List[int]]:
    from je_auto_control.utils.vision.vlm_api import locate_by_description
    coords = locate_by_description(description, screen_region=screen_region,
                                    model=model)
    return None if coords is None else [int(coords[0]), int(coords[1])]


def vlm_click(description: str,
              screen_region: Optional[List[int]] = None,
              model: Optional[str] = None) -> bool:
    from je_auto_control.utils.vision.vlm_api import click_by_description
    return bool(click_by_description(description,
                                      screen_region=screen_region,
                                      model=model))
