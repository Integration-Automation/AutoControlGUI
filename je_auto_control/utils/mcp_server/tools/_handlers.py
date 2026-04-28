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
                y: Optional[int] = None) -> List[Any]:
    from je_auto_control.wrapper.auto_control_mouse import click_mouse as _click
    keycode, click_x, click_y = _click(mouse_keycode, x, y)
    # Real wrapper resolves the string keycode to an int via the keys table;
    # the fake backend keeps it as a string. Pass through whatever we got.
    resolved = int(keycode) if isinstance(keycode, int) else keycode
    return [resolved, int(click_x), int(click_y)]


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
               screen_region: Optional[List[int]] = None,
               monitor_index: Optional[int] = None,
               ) -> List[MCPContent]:
    """Take a screenshot, optionally save it, and return image + path.

    When ``monitor_index`` is provided, capture that specific monitor
    via ``mss`` (works across multi-display setups). Index 0 is the
    virtual desktop spanning all monitors; 1+ are individual screens.
    """
    saved_path: Optional[str] = None
    if file_path is not None:
        saved_path = os.path.realpath(os.fspath(file_path))
        parent = os.path.dirname(saved_path) or "."
        if not os.path.isdir(parent):
            raise ValueError(f"screenshot directory does not exist: {parent}")
    if monitor_index is not None:
        image = _grab_monitor(int(monitor_index))
        if saved_path is not None:
            image.save(saved_path)
    else:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        image = pil_screenshot(file_path=saved_path, screen_region=screen_region)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    contents: List[MCPContent] = [MCPContent.image_block(encoded)]
    if saved_path is not None:
        contents.append(MCPContent.text_block(f"saved: {saved_path}"))
    return contents


def list_monitors() -> List[Dict[str, Any]]:
    """Return every monitor's geometry. Index 0 spans all monitors."""
    import mss
    with mss.mss() as sct:
        return [
            {
                "index": index, "left": int(monitor["left"]),
                "top": int(monitor["top"]),
                "width": int(monitor["width"]),
                "height": int(monitor["height"]),
                "is_combined": index == 0,
            }
            for index, monitor in enumerate(sct.monitors)
        ]


def _grab_monitor(index: int):
    """Capture a single monitor via ``mss`` and return a PIL Image."""
    import mss
    from PIL import Image
    with mss.mss() as sct:
        if index < 0 or index >= len(sct.monitors):
            raise ValueError(
                f"monitor index {index} out of range "
                f"(0..{len(sct.monitors) - 1})"
            )
        frame = sct.grab(sct.monitors[index])
        return Image.frombytes("RGB", frame.size, frame.bgra, "raw", "BGRX")


def get_pixel(x: int, y: int) -> List[int]:
    from je_auto_control.wrapper.auto_control_screen import get_pixel as _pixel
    pixel = _pixel(int(x), int(y))
    if pixel is None:
        return []
    return [int(component) for component in pixel]


def wait_for_image(image_path: str, timeout: float = 10.0,
                   poll: float = 0.5,
                   detect_threshold: float = 1.0,
                   ctx: Any = None) -> List[int]:
    """Poll for ``image_path`` on screen; return its centre [x, y] or raise."""
    import time as _time
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    from je_auto_control.wrapper.auto_control_image import locate_image_center as _loc
    poll_seconds = max(0.05, float(poll))
    deadline = _time.monotonic() + float(timeout)
    while _time.monotonic() < deadline:
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(_time.monotonic() - (deadline - float(timeout)),
                          total=float(timeout),
                          message=f"waiting for {image_path}")
        try:
            cx, cy = _loc(image_path,
                          detect_threshold=float(detect_threshold))
            return [int(cx), int(cy)]
        except ImageNotFoundException:
            _time.sleep(poll_seconds)
    raise TimeoutError(
        f"wait_for_image timed out after {timeout}s: {image_path!r}"
    )


def wait_for_pixel(x: int, y: int, target_rgb: List[int],
                   tolerance: int = 8, timeout: float = 10.0,
                   poll: float = 0.25,
                   ctx: Any = None) -> List[int]:
    """Poll until pixel ``(x, y)`` matches ``target_rgb`` within ``tolerance``."""
    import time as _time
    from je_auto_control.wrapper.auto_control_screen import get_pixel as _pixel
    if len(target_rgb) < 3:
        raise ValueError("target_rgb must contain at least 3 channels")
    target = [int(c) for c in target_rgb[:3]]
    tol = max(0, int(tolerance))
    poll_seconds = max(0.05, float(poll))
    deadline = _time.monotonic() + float(timeout)
    while _time.monotonic() < deadline:
        if ctx is not None:
            ctx.check_cancelled()
        raw = _pixel(int(x), int(y))
        if raw is not None and len(raw) >= 3:
            channels = [int(raw[i]) for i in range(3)]
            if all(abs(channels[i] - target[i]) <= tol for i in range(3)):
                return channels
        _time.sleep(poll_seconds)
    raise TimeoutError(
        f"wait_for_pixel timed out after {timeout}s at ({x}, {y})"
    )


def diff_screenshots(image_path_a: str,
                     image_path_b: str,
                     threshold: int = 16,
                     min_box_pixels: int = 25,
                     ) -> Dict[str, Any]:
    """Return the bounding boxes that differ between two screenshots.

    The result is JSON-friendly: ``{"size": [w, h], "boxes": [[x, y, w, h], ...]}``.
    Boxes are merged via a flood-fill so a single changed widget is one
    rectangle. Pixels whose absolute per-channel difference is at most
    ``threshold`` are considered equal; tiny components below
    ``min_box_pixels`` are dropped to ignore JPEG / antialias noise.
    """
    safe_a = os.path.realpath(os.fspath(image_path_a))
    safe_b = os.path.realpath(os.fspath(image_path_b))
    return _diff_screenshots(safe_a, safe_b, int(threshold),
                              int(min_box_pixels))


def _diff_screenshots(path_a: str, path_b: str, threshold: int,
                      min_box_pixels: int) -> Dict[str, Any]:
    """Implementation split off so the public adapter stays under 75 lines."""
    import numpy as np
    from PIL import Image

    img_a = np.asarray(Image.open(path_a).convert("RGB"))
    img_b = np.asarray(Image.open(path_b).convert("RGB"))
    if img_a.shape != img_b.shape:
        height = min(img_a.shape[0], img_b.shape[0])
        width = min(img_a.shape[1], img_b.shape[1])
        img_a = img_a[:height, :width]
        img_b = img_b[:height, :width]
    diff = np.abs(img_a.astype("int16") - img_b.astype("int16"))
    mask = (diff.max(axis=-1) > threshold).astype("uint8")
    boxes = _connected_component_boxes(mask, min_box_pixels)
    height, width = mask.shape
    return {"size": [int(width), int(height)], "boxes": boxes}


def _connected_component_boxes(mask: Any,
                               min_pixels: int) -> List[List[int]]:
    """Return tight bounding boxes for connected non-zero regions in ``mask``."""
    import numpy as np

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    boxes: List[List[int]] = []
    for start_y in range(height):
        for start_x in range(width):
            if mask[start_y, start_x] == 0 or visited[start_y, start_x]:
                continue
            box = _flood_fill_box(mask, visited, start_x, start_y)
            if box[2] * box[3] < min_pixels:
                continue
            boxes.append(box)
    return boxes


_screen_recorder_singleton: Any = None


def _get_screen_recorder() -> Any:
    """Lazy-init the process-wide ScreenRecorder."""
    global _screen_recorder_singleton
    if _screen_recorder_singleton is None:
        from je_auto_control.utils.cv2_utils.screen_record import ScreenRecorder
        _screen_recorder_singleton = ScreenRecorder()
    return _screen_recorder_singleton


def screen_record_start(recorder_name: str,
                        file_path: str,
                        codec: str = "XVID",
                        frame_per_sec: int = 30,
                        width: int = 1920,
                        height: int = 1080) -> str:
    """Start a screen recording under ``recorder_name``; returns the resolved path."""
    safe_path = os.path.realpath(os.fspath(file_path))
    parent = os.path.dirname(safe_path) or "."
    if not os.path.isdir(parent):
        raise ValueError(f"recording directory does not exist: {parent}")
    recorder = _get_screen_recorder()
    recorder.start_new_record(
        recorder_name=str(recorder_name),
        path_and_filename=safe_path, codec=str(codec),
        frame_per_sec=int(frame_per_sec),
        resolution=(int(width), int(height)),
    )
    return safe_path


def screen_record_stop(recorder_name: str) -> str:
    """Stop the named screen recording; no-op if it doesn't exist."""
    recorder = _get_screen_recorder()
    recorder.stop_record(str(recorder_name))
    return "stopped"


def screen_record_list() -> List[str]:
    """Return the names of currently running recorders."""
    recorder = _get_screen_recorder()
    return sorted(recorder.running_recorder.keys())


def _flood_fill_box(mask: Any, visited: Any,
                    start_x: int, start_y: int) -> List[int]:
    """Iterative 4-connectivity flood fill returning [x, y, w, h]."""
    height, width = mask.shape
    stack = [(start_x, start_y)]
    min_x = max_x = start_x
    min_y = max_y = start_y
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        if visited[y, x] or mask[y, x] == 0:
            continue
        visited[y, x] = True
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x
        if y < min_y:
            min_y = y
        if y > max_y:
            max_y = y
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return [int(min_x), int(min_y),
            int(max_x - min_x + 1), int(max_y - min_y + 1)]


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


def _resolve_window_hwnd(title_substring: str,
                         case_sensitive: bool) -> int:
    from je_auto_control.wrapper.auto_control_window import find_window
    hit = find_window(title_substring, case_sensitive=case_sensitive)
    if hit is None:
        raise ValueError(f"no window matches {title_substring!r}")
    return int(hit[0])


def window_move(title_substring: str, x: int, y: int,
                width: int, height: int,
                case_sensitive: bool = False) -> Dict[str, int]:
    """Move and resize the first window matching ``title_substring`` (Win32 only)."""
    from je_auto_control.windows.window import windows_window_manage as wm
    hwnd = _resolve_window_hwnd(title_substring, bool(case_sensitive))
    if not wm.move_window(hwnd, int(x), int(y), int(width), int(height)):
        raise RuntimeError("MoveWindow returned 0")
    return {"hwnd": hwnd, "x": int(x), "y": int(y),
            "width": int(width), "height": int(height)}


def _show_command(title_substring: str, case_sensitive: bool,
                  cmd_show: int) -> int:
    """Resolve the window then call ShowWindow with the given cmd."""
    from je_auto_control.windows.window import windows_window_manage as wm
    hwnd = _resolve_window_hwnd(title_substring, bool(case_sensitive))
    wm.show_window(hwnd, int(cmd_show))
    return hwnd


def window_minimize(title_substring: str,
                    case_sensitive: bool = False) -> int:
    return _show_command(title_substring, bool(case_sensitive), cmd_show=6)


def window_maximize(title_substring: str,
                    case_sensitive: bool = False) -> int:
    return _show_command(title_substring, bool(case_sensitive), cmd_show=3)


def window_restore(title_substring: str,
                   case_sensitive: bool = False) -> int:
    return _show_command(title_substring, bool(case_sensitive), cmd_show=9)


def launch_process(argv: List[str],
                   working_directory: Optional[str] = None,
                   ) -> Dict[str, Any]:
    """Spawn a detached subprocess with a sanitised argv list."""
    import subprocess  # nosec B404  # reason: required to spawn child processes
    if not isinstance(argv, list) or not argv:
        raise ValueError("argv must be a non-empty list")
    cleaned = [str(part) for part in argv]
    cwd = None
    if working_directory is not None:
        cwd = os.path.realpath(os.fspath(working_directory))
        if not os.path.isdir(cwd):
            raise ValueError(f"working_directory does not exist: {cwd}")
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    process = subprocess.Popen(  # nosec B603  # reason: argv list, no shell expansion
        cleaned, cwd=cwd, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )
    return {"pid": int(process.pid), "argv": cleaned}


def list_processes(name_contains: Optional[str] = None,
                    ) -> List[Dict[str, Any]]:
    """List running processes via ``psutil`` if installed; raise otherwise."""
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError(
            "ac_list_processes requires psutil — pip install psutil"
        ) from error
    needle = name_contains.lower() if name_contains else None
    out: List[Dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "username"]):
        info = proc.info or {}
        name = (info.get("name") or "")
        if needle and needle not in name.lower():
            continue
        out.append({
            "pid": int(info.get("pid") or 0),
            "name": name,
            "username": info.get("username") or "",
        })
    return out


def kill_process(pid: int, timeout: float = 5.0) -> str:
    """Terminate a PID gracefully, escalating to SIGKILL after ``timeout``."""
    try:
        import psutil  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError(
            "ac_kill_process requires psutil — pip install psutil"
        ) from error
    try:
        proc = psutil.Process(int(pid))
    except psutil.NoSuchProcess:
        return "not-found"
    proc.terminate()
    try:
        proc.wait(timeout=float(timeout))
        return "terminated"
    except psutil.TimeoutExpired:
        proc.kill()
        return "killed"


def shell_command(command: str, timeout: float = 30.0
                  ) -> Dict[str, Any]:
    """Run a shell-style command line and return stdout/stderr/exit_code.

    Uses argv-list parsing via ``shlex.split`` so we never enable a
    shell — protects against the parameterised command injection
    classes Bandit B602 / B605 cover.
    """
    import shlex
    import subprocess  # nosec B404  # reason: required for child execution

    if not command or not command.strip():
        raise ValueError("command must be a non-empty string")
    argv = shlex.split(command, posix=False) if os.name == "nt" \
        else shlex.split(command)
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
    proc = subprocess.run(  # nosec B603  # reason: argv from shlex.split, no shell
        argv, capture_output=True, text=True,
        timeout=float(timeout), check=False,
    )
    return {
        "exit_code": int(proc.returncode),
        "stdout": proc.stdout, "stderr": proc.stderr,
    }


def get_clipboard() -> str:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard as _get
    return _get()


def set_clipboard(text: str) -> str:
    from je_auto_control.utils.clipboard.clipboard import set_clipboard as _set
    _set(text)
    return "ok"


def get_clipboard_image() -> List[MCPContent]:
    """Return the clipboard image as a base64 PNG content block."""
    from je_auto_control.utils.clipboard.clipboard_image import (
        get_clipboard_image as _read,
    )
    payload = _read()
    if payload is None:
        return [MCPContent.text_block("clipboard does not contain an image")]
    encoded = base64.b64encode(payload).decode("ascii")
    return [MCPContent.image_block(encoded)]


def set_clipboard_image(image_path: str) -> str:
    from je_auto_control.utils.clipboard.clipboard_image import (
        set_clipboard_image as _write,
    )
    safe_path = os.path.realpath(os.fspath(image_path))
    _write(safe_path)
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


# === Scheduler / triggers / hotkey daemon ===================================

def _job_to_dict(job: Any) -> Dict[str, Any]:
    return {
        "job_id": job.job_id, "script_path": job.script_path,
        "interval_seconds": job.interval_seconds,
        "is_cron": job.is_cron, "repeat": job.repeat,
        "max_runs": job.max_runs, "runs": job.runs,
        "enabled": job.enabled,
    }


def scheduler_add_job(script_path: str,
                      interval_seconds: Optional[float] = None,
                      cron_expression: Optional[str] = None,
                      repeat: bool = True,
                      max_runs: Optional[int] = None,
                      job_id: Optional[str] = None) -> Dict[str, Any]:
    """Add an interval or cron job to the default scheduler."""
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    safe_path = os.path.realpath(os.fspath(script_path))
    if cron_expression:
        job = default_scheduler.add_cron_job(
            safe_path, cron_expression, max_runs=max_runs, job_id=job_id,
        )
        return _job_to_dict(job)
    if interval_seconds is None:
        raise ValueError("scheduler_add_job needs either interval_seconds or cron_expression")
    job = default_scheduler.add_job(
        safe_path, interval_seconds=float(interval_seconds),
        repeat=bool(repeat), max_runs=max_runs, job_id=job_id,
    )
    return _job_to_dict(job)


def scheduler_remove_job(job_id: str) -> bool:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    return bool(default_scheduler.remove_job(job_id))


def scheduler_list_jobs() -> List[Dict[str, Any]]:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    return [_job_to_dict(job) for job in default_scheduler.list_jobs()]


def scheduler_start() -> str:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    default_scheduler.start()
    return "started"


def scheduler_stop() -> str:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    default_scheduler.stop()
    return "stopped"


def _trigger_to_dict(trigger: Any) -> Dict[str, Any]:
    return {
        "trigger_id": trigger.trigger_id,
        "type": type(trigger).__name__,
        "script_path": trigger.script_path,
        "repeat": trigger.repeat, "enabled": trigger.enabled,
        "fired": trigger.fired,
    }


def trigger_add(kind: str, script_path: str, repeat: bool = False,
                image_path: Optional[str] = None,
                threshold: float = 0.8,
                title_substring: Optional[str] = None,
                case_sensitive: bool = False,
                x: int = 0, y: int = 0,
                target_rgb: Optional[List[int]] = None,
                tolerance: int = 8,
                watch_path: Optional[str] = None) -> Dict[str, Any]:
    """Add a trigger to the default engine. ``kind`` is image/window/pixel/file."""
    from je_auto_control.utils.triggers.trigger_engine import (
        FilePathTrigger, ImageAppearsTrigger, PixelColorTrigger,
        WindowAppearsTrigger, default_trigger_engine,
    )
    safe_script = os.path.realpath(os.fspath(script_path))
    trigger = _build_trigger(
        kind=kind, script_path=safe_script, repeat=repeat,
        image_path=image_path, threshold=threshold,
        title_substring=title_substring, case_sensitive=case_sensitive,
        x=x, y=y, target_rgb=target_rgb, tolerance=tolerance,
        watch_path=watch_path,
        types={
            "image": ImageAppearsTrigger,
            "window": WindowAppearsTrigger,
            "pixel": PixelColorTrigger,
            "file": FilePathTrigger,
        },
    )
    default_trigger_engine.add(trigger)
    return _trigger_to_dict(trigger)


def _build_trigger(*, kind: str, script_path: str, repeat: bool,
                   image_path: Optional[str], threshold: float,
                   title_substring: Optional[str], case_sensitive: bool,
                   x: int, y: int, target_rgb: Optional[List[int]],
                   tolerance: int, watch_path: Optional[str],
                   types: Dict[str, Any]) -> Any:
    if kind == "image":
        if not image_path:
            raise ValueError("image trigger requires image_path")
        return types["image"](trigger_id="", script_path=script_path,
                               repeat=repeat, image_path=image_path,
                               threshold=float(threshold))
    if kind == "window":
        if not title_substring:
            raise ValueError("window trigger requires title_substring")
        return types["window"](trigger_id="", script_path=script_path,
                                repeat=repeat,
                                title_substring=title_substring,
                                case_sensitive=bool(case_sensitive))
    if kind == "pixel":
        rgb = tuple(int(c) for c in (target_rgb or [0, 0, 0]))
        return types["pixel"](trigger_id="", script_path=script_path,
                               repeat=repeat, x=int(x), y=int(y),
                               target_rgb=rgb, tolerance=int(tolerance))
    if kind == "file":
        if not watch_path:
            raise ValueError("file trigger requires watch_path")
        return types["file"](trigger_id="", script_path=script_path,
                              repeat=repeat, watch_path=watch_path)
    raise ValueError(f"unknown trigger kind: {kind!r}")


def trigger_remove(trigger_id: str) -> bool:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    return bool(default_trigger_engine.remove(trigger_id))


def trigger_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    return [_trigger_to_dict(t) for t in default_trigger_engine.list_triggers()]


def trigger_start() -> str:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    default_trigger_engine.start()
    return "started"


def trigger_stop() -> str:
    from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
    default_trigger_engine.stop()
    return "stopped"


def hotkey_bind(combo: str, script_path: str,
                binding_id: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    safe_path = os.path.realpath(os.fspath(script_path))
    binding = default_hotkey_daemon.bind(combo, safe_path,
                                          binding_id=binding_id)
    return {
        "binding_id": binding.binding_id, "combo": binding.combo,
        "script_path": binding.script_path, "enabled": binding.enabled,
        "fired": binding.fired,
    }


def hotkey_unbind(binding_id: str) -> bool:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    return bool(default_hotkey_daemon.unbind(binding_id))


def hotkey_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    return [{
        "binding_id": b.binding_id, "combo": b.combo,
        "script_path": b.script_path, "enabled": b.enabled,
        "fired": b.fired,
    } for b in default_hotkey_daemon.list_bindings()]


def hotkey_daemon_start() -> str:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    default_hotkey_daemon.start()
    return "started"


def hotkey_daemon_stop() -> str:
    from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
    default_hotkey_daemon.stop()
    return "stopped"


# === Remote Desktop =========================================================

def remote_host_start(token: str, bind: str = "127.0.0.1",
                      port: int = 0, fps: float = 10.0,
                      quality: int = 70,
                      max_clients: int = 4,
                      host_id: Optional[str] = None) -> Dict[str, Any]:
    """Start the singleton TCP host (or restart if one is running)."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.start_host(
        token=token, bind=bind, port=int(port),
        fps=float(fps), quality=int(quality),
        max_clients=int(max_clients), host_id=host_id,
    )


def remote_host_stop(timeout: float = 2.0) -> Dict[str, Any]:
    """Stop the active TCP host (no-op when nothing is running)."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.stop_host(timeout=float(timeout))


def remote_host_status() -> Dict[str, Any]:
    """Snapshot the host registry: running, port, host_id, client count."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.host_status()


def remote_viewer_connect(host: str, port: int, token: str,
                          timeout: float = 5.0,
                          expected_host_id: Optional[str] = None,
                          ) -> Dict[str, Any]:
    """Open a viewer to a remote host and wait for the auth handshake."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.connect_viewer(
        host=host, port=int(port), token=token,
        timeout=float(timeout),
        expected_host_id=expected_host_id,
    )


def remote_viewer_disconnect(timeout: float = 2.0) -> Dict[str, Any]:
    """Close the active viewer (no-op when nothing is connected)."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.disconnect_viewer(timeout=float(timeout))


def remote_viewer_status() -> Dict[str, Any]:
    """Return the viewer registry snapshot: connected + remote host_id."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.viewer_status()


def remote_viewer_send_input(action: Dict[str, Any]) -> Dict[str, Any]:
    """Forward ``action`` (mouse_move / type / etc.) through the viewer."""
    from je_auto_control.utils.remote_desktop.registry import registry
    return registry.send_input(action)


# === Virtual gamepad (ViGEm) ================================================

def gamepad_press(button: str) -> Dict[str, Any]:
    """Press a virtual Xbox 360 button by friendly name."""
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().press_button(button)
    return {"button": button, "state": "down"}


def gamepad_release(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().release_button(button)
    return {"button": button, "state": "up"}


def gamepad_click(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().click_button(button)
    return {"button": button, "state": "click"}


def gamepad_dpad(direction: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_dpad(direction)
    return {"dpad": direction}


def gamepad_left_stick(x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_left_stick(int(x), int(y))
    return {"left_stick": [int(x), int(y)]}


def gamepad_right_stick(x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_right_stick(int(x), int(y))
    return {"right_stick": [int(x), int(y)]}


def gamepad_left_trigger(value: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_left_trigger(int(value))
    return {"left_trigger": int(value)}


def gamepad_right_trigger(value: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_right_trigger(int(value))
    return {"right_trigger": int(value)}


def gamepad_reset() -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().reset()
    return {"reset": True}
