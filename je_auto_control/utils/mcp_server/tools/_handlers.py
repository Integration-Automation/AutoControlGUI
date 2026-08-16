"""Adapter functions that bridge MCP tool calls to AutoControl's headless API.

Each adapter normalises arguments (parses ints / paths) and return
values (lists / dicts / strings, or :class:`MCPContent`) so they
survive the JSON-RPC boundary. Wrapper imports are lazy to keep the
top-level MCP server boot cheap.
"""
import base64
import io
import os
import threading
from typing import Any, Dict, List, Optional

from je_auto_control.utils.mcp_server.tools._base import MCPContent

_DEFAULT_APPROVALS_DIR = ".approvals"


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
        min_x, max_x = min(min_x, x), max(max_x, x)
        min_y, max_y = min(min_y, y), max(max_y, y)
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


def minimize_window(title_substring: str,
                    case_sensitive: bool = False) -> bool:
    from je_auto_control.wrapper.auto_control_window import (
        minimize_window_by_title,
    )
    return bool(minimize_window_by_title(title_substring,
                                         case_sensitive=case_sensitive))


def foreground_window() -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        foreground_window as _front,
    )
    hit = _front()
    return {"hwnd": 0, "title": ""} if hit is None else {"hwnd": hit[0],
                                                         "title": hit[1]}


def window_rect(title_substring: str,
                case_sensitive: bool = False) -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        window_rect as _rect,
    )
    rect = _rect(title_substring, case_sensitive=case_sensitive)
    return {"rect": list(rect) if rect is not None else None}


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


def open_path(target, verb="open"):
    from je_auto_control.utils.executor.action_executor import _open_path
    return _open_path(target, verb)


def plan_open(target, verb="open"):
    from je_auto_control.utils.executor.action_executor import _plan_open
    return _plan_open(target, verb)


def idle_seconds():
    from je_auto_control.utils.executor.action_executor import _idle_seconds
    return _idle_seconds()


def is_idle(threshold):
    from je_auto_control.utils.executor.action_executor import _is_idle
    return _is_idle(threshold)


def plan_keep_awake(display=True, system=True):
    from je_auto_control.utils.executor.action_executor import _plan_keep_awake
    return _plan_keep_awake(display, system)


def keep_awake_on(display=True, system=True):
    from je_auto_control.utils.executor.action_executor import _keep_awake_on
    return _keep_awake_on(display, system)


def allow_sleep():
    from je_auto_control.utils.executor.action_executor import _allow_sleep
    return _allow_sleep()


def get_volume():
    from je_auto_control.utils.executor.action_executor import _get_volume
    return _get_volume()


def set_volume(level):
    from je_auto_control.utils.executor.action_executor import _set_volume
    return _set_volume(level)


def change_volume(delta):
    from je_auto_control.utils.executor.action_executor import _change_volume
    return _change_volume(delta)


def set_mute(muted=True):
    from je_auto_control.utils.executor.action_executor import _set_mute
    return _set_mute(muted)


def toggle_mute():
    from je_auto_control.utils.executor.action_executor import _toggle_mute
    return _toggle_mute()


def lock_session():
    from je_auto_control.utils.executor.action_executor import _lock_session
    return _lock_session()


def plan_lock_session():
    from je_auto_control.utils.executor.action_executor import (
        _plan_lock_session,
    )
    return _plan_lock_session()


def wait_for_unlock(timeout=30.0, interval=0.5):
    from je_auto_control.utils.executor.action_executor import _wait_for_unlock
    return _wait_for_unlock(timeout, interval)


def classify_lock_transitions(states):
    from je_auto_control.utils.executor.action_executor import (
        _classify_lock_transitions,
    )
    return _classify_lock_transitions(states)


def ime_state():
    from je_auto_control.utils.executor.action_executor import _ime_state
    return _ime_state()


def is_composing():
    from je_auto_control.utils.executor.action_executor import _is_composing
    return _is_composing()


def wait_for_composition_commit(timeout=5.0, interval=0.1):
    from je_auto_control.utils.executor.action_executor import (
        _wait_for_composition_commit,
    )
    return _wait_for_composition_commit(timeout, interval)


def decode_conversion_mode(flags):
    from je_auto_control.utils.executor.action_executor import (
        _decode_conversion_mode,
    )
    return _decode_conversion_mode(flags)


def retry_delay(attempt, base=0.1, max_delay=5.0, multiplier=2.0,
                jitter="none"):
    from je_auto_control.utils.executor.action_executor import _retry_delay
    return _retry_delay(attempt, base, max_delay, multiplier, jitter)


def plan_retry_delays(attempts, base=0.1, max_delay=5.0, multiplier=2.0,
                      jitter="none"):
    from je_auto_control.utils.executor.action_executor import (
        _plan_retry_delays,
    )
    return _plan_retry_delays(attempts, base, max_delay, multiplier, jitter)


def compare_field_value(expected, actual, mode="exact"):
    from je_auto_control.utils.executor.action_executor import (
        _compare_field_value,
    )
    return _compare_field_value(expected, actual, mode)


def verify_field_value(expected, name=None, role=None, app_name=None,
                       automation_id=None, mode="exact"):
    from je_auto_control.utils.executor.action_executor import (
        _verify_field_value,
    )
    return _verify_field_value(expected, name, role, app_name, automation_id,
                               mode)


def adaptive_timeout(durations, percentile_q=95.0, factor=1.5, min_s=1.0,
                     max_s=60.0):
    from je_auto_control.utils.executor.action_executor import (
        _adaptive_timeout,
    )
    return _adaptive_timeout(durations, percentile_q, factor, min_s, max_s)


def timeout_stats(durations, percentile_q=95.0, factor=1.5, min_s=1.0,
                  max_s=60.0):
    from je_auto_control.utils.executor.action_executor import _timeout_stats
    return _timeout_stats(durations, percentile_q, factor, min_s, max_s)


def ensure_field_value(desired, name=None, role=None, app_name=None,
                       automation_id=None, attempts=2):
    from je_auto_control.utils.executor.action_executor import (
        _ensure_field_value,
    )
    return _ensure_field_value(desired, name, role, app_name, automation_id,
                               attempts)


def wait_until_app_idle(quiet_samples=3, timeout=10.0, interval=0.1):
    from je_auto_control.utils.executor.action_executor import (
        _wait_until_app_idle,
    )
    return _wait_until_app_idle(quiet_samples, timeout, interval)


def idle_point(busy_samples, quiet_samples=3):
    from je_auto_control.utils.executor.action_executor import _idle_point
    return _idle_point(busy_samples, quiet_samples)


def simulate_cvd(rgb, kind="deuteranopia", severity=1.0):
    from je_auto_control.utils.executor.action_executor import _simulate_cvd
    return _simulate_cvd(rgb, kind, severity)


def colors_collide(left, right, kind="deuteranopia", severity=1.0,
                   threshold=40.0):
    from je_auto_control.utils.executor.action_executor import _colors_collide
    return _colors_collide(left, right, kind, severity, threshold)


def place_labels(marks, label_width=22, label_height=16, bounds=None):
    from je_auto_control.utils.executor.action_executor import _place_labels
    return _place_labels(marks, label_width, label_height, bounds)


def label_color(background):
    from je_auto_control.utils.executor.action_executor import _label_color
    return _label_color(background)


def grade_contrast(foreground, background):
    from je_auto_control.utils.executor.action_executor import _grade_contrast
    return _grade_contrast(foreground, background)


def dominant_pair(pixels):
    from je_auto_control.utils.executor.action_executor import _dominant_pair
    return _dominant_pair(pixels)


def region_contrast(region=None):
    from je_auto_control.utils.executor.action_executor import _region_contrast
    return _region_contrast(region)


def match_theme(template, region=None, method="sobel", min_score=0.5):
    from je_auto_control.utils.executor.action_executor import _match_theme
    return _match_theme(template, region, method, min_score)


def rank_changes(scored_boxes, threshold=0.1):
    from je_auto_control.utils.executor.action_executor import _rank_changes
    return _rank_changes(scored_boxes, threshold)


def localize_changes(reference, boxes, current=None, threshold=0.1,
                     region=None):
    from je_auto_control.utils.executor.action_executor import (
        _localize_changes,
    )
    return _localize_changes(reference, boxes, current, threshold, region)


def classify_widget(features):
    from je_auto_control.utils.executor.action_executor import _classify_widget
    return _classify_widget(features)


def classify_icon(source, box):
    from je_auto_control.utils.executor.action_executor import _classify_icon
    return _classify_icon(source, box)


def propose_elements(region=None, min_area=80, iou_threshold=0.5):
    from je_auto_control.utils.executor.action_executor import (
        _propose_elements,
    )
    return _propose_elements(region, min_area, iou_threshold)


def tag_kinds(elements):
    from je_auto_control.utils.executor.action_executor import _tag_kinds
    return _tag_kinds(elements)


def act_in_view(target, kind="image", direction="down", max_scrolls=10,
                scroll_amount=3, button="left"):
    from je_auto_control.utils.executor.action_executor import _act_in_view
    return _act_in_view(target, kind, direction, max_scrolls, scroll_amount,
                        button)


def act_with_mode(x, y, mode="auto", button="left"):
    from je_auto_control.utils.executor.action_executor import _act_with_mode
    return _act_with_mode(x, y, mode, button)


def normalize_ext(target):
    from je_auto_control.utils.executor.action_executor import _normalize_ext
    return _normalize_ext(target)


def file_association(target):
    from je_auto_control.utils.executor.action_executor import _file_association
    return _file_association(target)


def get_clipboard() -> str:
    from je_auto_control.utils.clipboard.clipboard import get_clipboard as _get
    return _get()


def set_clipboard(text: str) -> str:
    from je_auto_control.utils.clipboard.clipboard import set_clipboard as _set
    _set(text)
    return "ok"


def get_clipboard_image() -> List[MCPContent]:
    """Return the clipboard image as a base64 PNG content block."""
    from je_auto_control.utils.clipboard.clipboard import (
        get_clipboard_image as _read,
    )
    payload = _read()
    if payload is None:
        return [MCPContent.text_block("clipboard does not contain an image")]
    encoded = base64.b64encode(payload).decode("ascii")
    return [MCPContent.image_block(encoded)]


def set_clipboard_image(image_path: str) -> str:
    from je_auto_control.utils.clipboard.clipboard import (
        set_clipboard_image as _write,
    )
    _write(os.path.realpath(os.fspath(image_path)))
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


def record_stop_timeline() -> List[Any]:
    from je_auto_control.wrapper.auto_control_record import (
        stop_record_timeline,
    )
    return stop_record_timeline() or []


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


def dedupe_moves(actions: List[Any],
                 move_commands: Optional[List[str]] = None) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import dedupe_moves as _dedupe
    return _dedupe(actions, move_commands=move_commands)


def merge_sleeps(actions: List[Any]) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import merge_sleeps as _merge
    return _merge(actions)


# === Semantic locators (a11y / VLM) =========================================

def a11y_list(app_name: Optional[str] = None,
              max_results: int = 100,
              window_title: Optional[str] = None) -> List[Dict[str, Any]]:
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements,
    )
    return [element.to_dict()
            for element in list_accessibility_elements(
                app_name=app_name, max_results=int(max_results),
                window_title=window_title,
            )]


def a11y_find(name: Optional[str] = None,
              role: Optional[str] = None,
              app_name: Optional[str] = None,
              window_title: Optional[str] = None,
              contains: bool = False) -> Optional[Dict[str, Any]]:
    from je_auto_control.utils.accessibility import accessibility_api as api
    element = api.find_accessibility_element(
        name=name, role=role, app_name=app_name, window_title=window_title,
        contains=bool(contains))
    return None if element is None else element.to_dict()


def a11y_find_all(name: Optional[str] = None,
                  role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  window_title: Optional[str] = None,
                  contains: bool = False,
                  max_results: int = 50,
                  scan_limit: int = 1500) -> List[Dict[str, Any]]:
    from je_auto_control.utils.accessibility import accessibility_api as api
    return [element.to_dict() for element in api.find_accessibility_elements(
        name=name, role=role, app_name=app_name, window_title=window_title,
        contains=bool(contains), max_results=int(max_results),
        scan_limit=int(scan_limit))]


def a11y_click(name: Optional[str] = None,
               role: Optional[str] = None,
               app_name: Optional[str] = None) -> bool:
    from je_auto_control.utils.accessibility.accessibility_api import (
        click_accessibility_element,
    )
    return bool(click_accessibility_element(name=name, role=role,
                                             app_name=app_name))


def control_get_value(name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.accessibility import control_get_value as _g
    return _g(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_get_state(name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.accessibility import control_get_state as _g
    return _g(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_set_value(value, name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.accessibility import control_set_value as _s
    return _s(value, name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_invoke(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.accessibility import control_invoke as _i
    return _i(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_toggle(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.accessibility import control_toggle as _t
    return _t(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def read_table(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.accessibility import read_control_table as _r
    return _r(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def expand_control(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _expand_control
    return _expand_control(name, role, app_name, automation_id)


def collapse_control(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _collapse_control
    return _collapse_control(name, role, app_name, automation_id)


def control_expand_state(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _control_expand_state)
    return _control_expand_state(name, role, app_name, automation_id)


def select_control_item(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _select_control_item
    return _select_control_item(name, role, app_name, automation_id)


def control_range(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _control_range
    return _control_range(name, role, app_name, automation_id)


def set_control_range(value, name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.executor.action_executor import _set_control_range
    return _set_control_range(value, name, role, app_name, automation_id)


def scroll_control_into_view(name=None, role=None, app_name=None,
                             automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _scroll_control_into_view)
    return _scroll_control_into_view(name, role, app_name, automation_id)


def get_control_text(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_control_text
    return _get_control_text(name, role, app_name, automation_id)


def find_control_text(text, ignore_case=True, name=None, role=None,
                      app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _find_control_text
    return _find_control_text(text, ignore_case, name, role, app_name,
                              automation_id)


def select_control_text(text, ignore_case=True, name=None, role=None,
                        app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _select_control_text)
    return _select_control_text(text, ignore_case, name, role, app_name,
                                automation_id)


def control_text_attributes(name=None, role=None, app_name=None,
                            automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _control_text_attributes)
    return _control_text_attributes(name, role, app_name, automation_id)


def realize_item(item_name, by="name", container_name=None, container_role=None,
                 app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _realize_item
    return _realize_item(item_name, by, container_name, container_role,
                         app_name, automation_id)


def get_element_properties(name=None, role=None, app_name=None,
                           automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _get_element_properties)
    return _get_element_properties(name, role, app_name, automation_id)


def table_headers(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _table_headers
    return _table_headers(name, role, app_name, automation_id)


def table_cell(row, column, name=None, role=None, app_name=None,
               automation_id=None):
    from je_auto_control.utils.executor.action_executor import _table_cell
    return _table_cell(row, column, name, role, app_name, automation_id)


def cell_by_header(row, column_header, name=None, role=None, app_name=None,
                   automation_id=None):
    from je_auto_control.utils.executor.action_executor import _cell_by_header
    return _cell_by_header(row, column_header, name, role, app_name,
                           automation_id)


def move_element(x, y, name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _move_element
    return _move_element(x, y, name, role, app_name, automation_id)


def resize_element(width, height, name=None, role=None, app_name=None,
                   automation_id=None):
    from je_auto_control.utils.executor.action_executor import _resize_element
    return _resize_element(width, height, name, role, app_name, automation_id)


def set_window_state(state, name=None, role=None, app_name=None,
                     automation_id=None):
    from je_auto_control.utils.executor.action_executor import _set_window_state
    return _set_window_state(state, name, role, app_name, automation_id)


def window_interaction_state(name=None, role=None, app_name=None,
                             automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _window_interaction_state)
    return _window_interaction_state(name, role, app_name, automation_id)


def legacy_info(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _legacy_info
    return _legacy_info(name, role, app_name, automation_id)


def legacy_default_action(name=None, role=None, app_name=None,
                          automation_id=None):
    from je_auto_control.utils.executor.action_executor import (
        _legacy_default_action)
    return _legacy_default_action(name, role, app_name, automation_id)


def get_selection(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_selection
    return _get_selection(name, role, app_name, automation_id)


def list_views(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _list_views
    return _list_views(name, role, app_name, automation_id)


def set_view(view, name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _set_view
    return _set_view(view, name, role, app_name, automation_id)


def wait_for_focus_change(timeout=5.0):
    from je_auto_control.utils.executor.action_executor import (
        _wait_for_focus_change)
    return _wait_for_focus_change(timeout)


def get_selected_text(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_selected_text
    return _get_selected_text(name, role, app_name, automation_id)


def get_visible_text(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _get_visible_text
    return _get_visible_text(name, role, app_name, automation_id)


def watchdog_add(title, action="close", case_sensitive=False, name=None):
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.add_window_rule(
        title, action=action, case_sensitive=bool(case_sensitive), name=name)
    return {"rules": default_popup_watchdog.rule_names()}


def watchdog_start():
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.start()
    return {"running": True}


def watchdog_stop():
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.stop()
    return {"running": False}


def watchdog_list():
    from je_auto_control.utils.watchdog import default_popup_watchdog
    w = default_popup_watchdog
    return {"running": w.running, "rules": w.rule_names(), "hits": w.hits}


def generate_otp(secret, step=30, digits=6):
    from je_auto_control.utils.otp import generate_totp
    return generate_totp(secret, step=int(step), digits=int(digits))


def handle_file_dialog(path, action="open", window_title=None,
                       timeout_s=10.0, confirm_key="enter"):
    from je_auto_control.utils.file_dialog import handle_file_dialog as _h
    return _h(path, action=action, window_title=window_title,
              timeout_s=float(timeout_s), confirm_key=confirm_key)


def assert_session_active():
    from je_auto_control.utils.session_guard import ensure_interactive_session
    return {"interactive": ensure_interactive_session()}


def _work_queue(db, name):
    from je_auto_control.utils.work_queue import WorkQueue
    return WorkQueue(db, name)


def queue_add(db, data, reference=None, name="default"):
    return {"id": _work_queue(db, name).add(data, reference=reference)}


def queue_next(db, name="default"):
    item = _work_queue(db, name).get_next()
    return None if item is None else {
        "id": item.id, "reference": item.reference, "data": item.data,
        "status": item.status, "retries": item.retries}


def queue_complete(db, item_id, output=None, name="default"):
    _work_queue(db, name).complete(int(item_id), output=output)
    return {"id": int(item_id), "status": "success"}


def queue_fail(db, item_id, error, kind="application", max_retries=3,
               name="default"):
    status = _work_queue(db, name).fail(int(item_id), str(error),
                                        kind=str(kind),
                                        max_retries=int(max_retries))
    return {"id": int(item_id), "status": status}


def queue_stats(db, name="default"):
    return _work_queue(db, name).stats()


def generate_data(schema, count=10, path=None, fmt=None, seed=None):
    from je_auto_control.utils.test_data import generate_rows, write_dataset
    rows = generate_rows(schema, int(count), seed=seed)
    if path:
        return {"path": write_dataset(rows, path, fmt), "count": len(rows)}
    return {"rows": rows, "count": len(rows)}


def mcp_manifest(path=None, include_tools=False):
    from je_auto_control.utils.mcp_registry import (
        build_server_manifest, write_server_manifest)
    if path:
        return {"path": write_server_manifest(
            path, include_tools=bool(include_tools))}
    return {"manifest": build_server_manifest(
        include_tools=bool(include_tools))}


def rank_tests(flows, history_path=None, window=10):
    from je_auto_control.utils.test_select import rank_flows
    return {"ranked": rank_flows(flows, history_path=history_path,
                                 window=int(window))}


def select_tests(flows, k=None, threshold=None, history_path=None, window=10):
    from je_auto_control.utils.test_select import select_flows
    return {"selected": select_flows(
        flows, k=k, threshold=threshold, history_path=history_path,
        window=int(window))}


def _element_repo(path):
    from je_auto_control.utils.element_repository import ElementRepository
    return ElementRepository(path)


def element_save(path, key, name=None, role=None, app_name=None):
    return {"locator": _element_repo(path).save(
        key, name=name, role=role, app_name=app_name)}


def element_find(path, key):
    return _element_repo(path).find_info(key)


def element_click(path, key):
    return {"clicked": _element_repo(path).click(key)}


def element_remove(path, key):
    return {"removed": _element_repo(path).remove(key)}


def element_list(path):
    return {"keys": _element_repo(path).keys()}


def debug_trace(actions, dry_run=False):
    from je_auto_control.utils.flow_debugger import trace_actions
    return {"trace": trace_actions(actions, dry_run=bool(dry_run))}


def _skill_lib(path):
    from je_auto_control.utils.skill_library import SkillLibrary
    return SkillLibrary(path)


def skill_save(path, name, actions, description="", tags=None):
    skill = _skill_lib(path).save(name, actions, description=description,
                                  tags=tags)
    return {"name": skill.name, "tags": skill.tags}


def skill_run(path, name):
    return {"record": _skill_lib(path).run(name)}


def skill_list(path):
    return {"names": _skill_lib(path).names()}


def skill_remove(path, name):
    return {"removed": _skill_lib(path).remove(name)}


def skill_search(path, query):
    return {"names": [s.name for s in _skill_lib(path).search(query)]}


def guard_text(text, threshold=2):
    from je_auto_control.utils.guardrail import assess_text
    return assess_text(text, threshold=int(threshold))


def agent_card(path=None):
    from je_auto_control.utils.a2a import build_agent_card, write_agent_card
    if path:
        return {"path": write_agent_card(path)}
    return {"card": build_agent_card()}


def read_workbook(path, sheet=""):
    from je_auto_control.utils.office import read_workbook as _read
    return {"rows": _read(path, sheet=sheet)}


def write_workbook(path, rows, sheet="Sheet1"):
    from je_auto_control.utils.office import write_workbook as _write
    return {"path": _write(path, rows, sheet=sheet)}


def read_document(path):
    from je_auto_control.utils.office import read_document as _read
    return _read(path)


def write_document(path, paragraphs):
    from je_auto_control.utils.office import write_document as _write
    return {"path": _write(path, paragraphs)}


def read_presentation(path):
    from je_auto_control.utils.office import read_presentation as _read
    return _read(path)


def write_presentation(path, slides):
    from je_auto_control.utils.office import write_presentation as _write
    return {"path": _write(path, slides)}


def _agent_memory(db):
    from je_auto_control.utils.agent_memory import AgentMemory
    return AgentMemory(db)


def _episode_dict(episode):
    return {"id": episode.id, "goal": episode.goal, "steps": episode.steps,
            "outcome": episode.outcome, "tags": episode.tags,
            "score": episode.score}


def memory_remember(db, goal, steps=None, outcome="", tags=None):
    return {"id": _agent_memory(db).remember(
        goal, steps=steps, outcome=outcome, tags=tags)}


def memory_recall(db, query, limit=5):
    eps = _agent_memory(db).recall(query, limit=int(limit))
    return {"episodes": [_episode_dict(ep) for ep in eps]}


def memory_recent(db, limit=10):
    eps = _agent_memory(db).recent(limit=int(limit))
    return {"episodes": [_episode_dict(ep) for ep in eps]}


def memory_forget(db, episode_id):
    return {"removed": _agent_memory(db).forget(int(episode_id))}


def memory_stats(db):
    return _agent_memory(db).stats()


def seed_everything(seed=0):
    from je_auto_control.utils.deterministic import seed_everything as _seed
    return {"seed": _seed(int(seed))}


def _observe_predicate(kind, params):
    from je_auto_control.utils.observer import (
        image_predicate, pixel_predicate, text_predicate)
    builders = {
        "image": lambda: image_predicate(params.get("image", ""),
                                         params.get("threshold", 0.8)),
        "text": lambda: text_predicate(params.get("text", "")),
        "pixel": lambda: pixel_predicate(int(params.get("x", 0)),
                                         int(params.get("y", 0))),
    }
    if kind not in builders:
        raise ValueError(f"unknown observe kind: {kind!r}")
    return builders[kind]()


def _observe_handler(actions):
    from je_auto_control.utils.executor.action_executor import executor

    def handler(_event, _value):
        if actions:
            executor.execute_action(list(actions))
    return handler


def observe_add(name, kind="image", event="appear", actions=None, **params):
    from je_auto_control.utils.observer import default_observer
    default_observer.add(name, _observe_predicate(kind, params),
                         _observe_handler(actions or []), events=(event,))
    return {"name": name, "kind": kind, "event": event}


def observe_remove(name):
    from je_auto_control.utils.observer import default_observer
    return {"removed": default_observer.remove(name)}


def observe_list():
    from je_auto_control.utils.observer import default_observer
    return {"names": default_observer.names()}


def observe_poll():
    from je_auto_control.utils.observer import default_observer
    return {"fired": default_observer.poll_once()}


def observe_start():
    from je_auto_control.utils.observer import default_observer
    default_observer.start()
    return {"running": default_observer.running}


def observe_stop():
    from je_auto_control.utils.observer import default_observer
    default_observer.stop()
    return {"running": default_observer.running}


def generate_sbom(path=None, root="je_auto_control"):
    from je_auto_control.utils.sbom import build_sbom, write_sbom
    root_arg = root or None
    if path:
        return {"path": write_sbom(path, root_arg)}
    return {"sbom": build_sbom(root_arg)}


def shard_suite(flows, shards=2, history_path=None, window=20):
    from je_auto_control.utils.test_shard import shard_flows
    return {"shards": shard_flows(flows, int(shards),
                                  history_path=history_path,
                                  window=int(window))}


def merge_results(reports):
    from je_auto_control.utils.test_shard import merge_results as _merge
    return _merge(reports)


def validate_rows(rows, schema):
    from je_auto_control.utils.data_quality import validate_rows as _validate
    return _validate(rows, schema)


def extract_fields(text, fields=None, patterns=None):
    from je_auto_control.utils.data_quality import extract_fields as _extract
    return {"fields": _extract(text, fields=fields, patterns=patterns)}


def mask_rows(rows, rules):
    from je_auto_control.utils.data_quality import mask_rows as _mask
    return {"rows": _mask(rows, rules)}


def pseudo_localize(text=None, mapping=None, expansion=0.4):
    from je_auto_control.utils.i18n_test import (
        pseudo_localize as _pl, pseudo_localize_catalog as _plc)
    if mapping is not None:
        return {"catalog": _plc(mapping, expansion=float(expansion))}
    return {"text": _pl(text or "", expansion=float(expansion))}


def check_overflow(elements=None, avg_char_px=7.0, app_name=None):
    from je_auto_control.utils.i18n_test import check_overflow as _co
    items = elements
    if items is None:
        from je_auto_control.utils.accessibility.accessibility_api import (
            list_accessibility_elements)
        items = list_accessibility_elements(app_name=app_name)
    return {"issues": _co(items, avg_char_px=float(avg_char_px))}


def check_catalog(base, target):
    from je_auto_control.utils.i18n_test import check_catalog as _cc
    return _cc(base, target)


def run_resumable(actions, run_id, db, variables=None):
    from je_auto_control.utils.checkpoint import (
        CheckpointStore, run_resumable as _run)
    return _run(actions, run_id=run_id, store=CheckpointStore(db),
                variables=variables)


def checkpoint_status(run_id, db):
    from je_auto_control.utils.checkpoint import CheckpointStore
    cp = CheckpointStore(db).load(run_id)
    if cp is None:
        return {"checkpoint": None}
    return {"checkpoint": {"run_id": cp.run_id, "step_index": cp.step_index,
                           "variables": cp.variables}}


def checkpoint_clear(run_id, db):
    from je_auto_control.utils.checkpoint import CheckpointStore
    return {"cleared": CheckpointStore(db).clear(run_id)}


def mark_screen(app_name=None, render_path=None):
    from je_auto_control.utils.set_of_marks import mark_screen as _ms
    return _ms(app_name=app_name, render_path=render_path)


def mark_click(mark_id):
    from je_auto_control.utils.set_of_marks import mark_click as _mc
    return {"clicked": _mc(int(mark_id))}


def screen_snapshot(app_name=None):
    from je_auto_control.utils.screen_state import snapshot_screen
    return {"snapshot": snapshot_screen(app_name=app_name)}


def screen_diff(before, after):
    from je_auto_control.utils.screen_state import diff_snapshots
    return diff_snapshots(before, after)


def screen_changed(app_name=None):
    from je_auto_control.utils.screen_state import screen_changed as _sc
    return _sc(app_name=app_name)


def describe_screen(app_name=None):
    from je_auto_control.utils.screen_state import describe_screen as _ds
    return _ds(app_name=app_name)


def replay_timeline(events, speed=1.0):
    from je_auto_control.utils.input_macro import replay_timeline as _rt
    return {"played": _rt(events, speed=float(speed))}


def input_sequence(steps):
    from je_auto_control.utils.input_macro import run_sequence as _rs
    return {"log": _rs(steps)}


def circuit_call(name, actions, threshold=5, reset_s=30.0):
    from je_auto_control.utils.executor.action_executor import _circuit_call
    return _circuit_call(name, actions, threshold=int(threshold),
                         reset_s=float(reset_s))


def ci_annotations(annotations):
    from je_auto_control.utils.ci_annotations import emit_annotations
    return {"lines": emit_annotations(annotations)}


def clip_history_capture():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    return {"added": default_clipboard_history.capture_once()}


def clip_history_list():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    return {"history": default_clipboard_history.snapshot()}


def clip_history_search(query):
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    return {"matches": default_clipboard_history.search(query)}


def clip_history_start():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    default_clipboard_history.start()
    return {"running": default_clipboard_history.running}


def clip_history_stop():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    default_clipboard_history.stop()
    return {"running": default_clipboard_history.running}


def heal_stats(limit=200):
    from je_auto_control.utils.heal_analytics import analyze_heal_log
    return analyze_heal_log(limit=int(limit))


def scan_secrets(data):
    from je_auto_control.utils.secrets_scan import scan_secrets as _scan
    return {"findings": _scan(data)}


def generate_sop(actions, title="Automation Procedure", path=None):
    from je_auto_control.utils.process_doc import generate_sop as _gen
    from je_auto_control.utils.process_doc import write_sop as _write
    if path:
        return {"path": _write(actions, path, title=title)}
    return _gen(actions, title=title)


def tween_drag(start, end, steps=30, easing="ease_in_out_quad",
               button="mouse_left"):
    from je_auto_control.utils.tween_drag import tween_drag as _td
    return {"points": _td(tuple(start), tuple(end), steps=int(steps),
                          easing=easing, button=button)["points"]}


def list_plugins(group="je_auto_control.commands"):
    from je_auto_control.utils.plugin_sdk import discover_plugins
    return {"commands": sorted(discover_plugins(group))}


def load_plugins(group="je_auto_control.commands"):
    from je_auto_control.utils.plugin_sdk import load_plugins as _load
    return {"loaded": _load(group)}


def approval_request(action: str, requester: str = "",
                     db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    return {"token": ApprovalGate(db).request(action, requester)}


def approval_approve(token: str, approver: str, db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    return {"approved": ApprovalGate(db).approve(token, approver)}


def approval_reject(token: str, approver: str, db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    return {"rejected": ApprovalGate(db).reject(token, approver)}


def approval_status(token: str, db: Optional[str] = None):
    from je_auto_control.utils.governance import ApprovalGate
    gate = ApprovalGate(db)
    return {"status": gate.status(token), "approved": gate.is_approved(token)}


def lease_secret(name: str, ttl: float = 300.0):
    from je_auto_control.utils.governance import default_broker
    return {"token": default_broker.lease(name, ttl), "ttl": float(ttl)}


def lease_valid(token: str):
    from je_auto_control.utils.governance import default_broker
    return {"valid": default_broker.is_valid(token)}


def revoke_lease(token: str):
    from je_auto_control.utils.governance import default_broker
    return {"revoked": default_broker.revoke(token)}


def lease_active():
    from je_auto_control.utils.governance import default_broker
    return {"leases": default_broker.active()}


def egress_allow(allow=None, deny=None):
    from je_auto_control.utils.egress import set_egress_policy
    policy = set_egress_policy(allow, deny)
    return {"allow": policy.allow, "deny": policy.deny}


def egress_check(url: str):
    from je_auto_control.utils.egress import get_egress_policy
    return {"allowed": get_egress_policy().is_allowed(url)}


def egress_reset():
    from je_auto_control.utils.egress import set_egress_policy
    set_egress_policy(None, None)
    return {"allow": None, "deny": []}


def verify_artifact(name: str, content, approvals_dir: str = _DEFAULT_APPROVALS_DIR,
                    extension: str = "txt"):
    from je_auto_control.utils.approval import verify_artifact as _verify
    result = _verify(name, content, approvals_dir, extension)
    return {"status": result.status, "match": result.match,
            "approved_path": result.approved_path,
            "received_path": result.received_path}


def approve_artifact(name: str, approvals_dir: str = _DEFAULT_APPROVALS_DIR,
                     extension: str = "txt"):
    from je_auto_control.utils.approval import approve_artifact as _approve
    return {"approved": _approve(name, approvals_dir, extension)}


def pending_artifacts(approvals_dir: str = _DEFAULT_APPROVALS_DIR):
    from je_auto_control.utils.approval import pending_artifacts as _pending
    return {"pending": _pending(approvals_dir)}


def evaluate_trajectory(trajectory, rubric):
    from je_auto_control.utils.trajectory_eval import (
        evaluate_trajectory as _evaluate)
    return _evaluate(trajectory, rubric)


def compliance_report(evidence, frameworks=None, path=None, fmt="json"):
    from je_auto_control.utils.compliance import (
        build_compliance_report, write_compliance_report)
    report = build_compliance_report(evidence, frameworks)
    if path:
        report["path"] = write_compliance_report(report, path, fmt)
    return report


def trace_record(operation, model=None, system=None, input_tokens=None,
                 output_tokens=None, tool_name=None, duration_s=0.0,
                 status="ok"):
    from je_auto_control.utils.agent_trace import default_trace
    return default_trace.record(
        operation, model=model, system=system, input_tokens=input_tokens,
        output_tokens=output_tokens, tool_name=tool_name,
        duration_s=duration_s, status=status)


def trace_summary():
    from je_auto_control.utils.agent_trace import default_trace
    return default_trace.summary()


def trace_export():
    from je_auto_control.utils.agent_trace import default_trace
    return {"spans": default_trace.to_otel()}


def trace_reset():
    from je_auto_control.utils.agent_trace import reset_trace
    reset_trace()
    return {"reset": True}


def write_step_video(steps, output, fps=10, seconds_per_step=2.0):
    from je_auto_control.utils.video_report import (
        write_step_video as _write)
    return _write(steps, output, fps=fps, seconds_per_step=seconds_per_step)


def fuzzy_ratio(left, right, ignore_case=True):
    from je_auto_control.utils.fuzzy import fuzzy_ratio as _ratio
    return {"score": _ratio(left, right, ignore_case=ignore_case)}


def fuzzy_best_match(query, choices, score_cutoff=0.0, ignore_case=True):
    from je_auto_control.utils.fuzzy import fuzzy_best_match as _best
    best = _best(query, choices, score_cutoff=score_cutoff,
                 ignore_case=ignore_case)
    if best is None:
        return {"match": None, "score": 0.0, "index": -1}
    return {"match": best[0], "score": best[1], "index": best[2]}


def fuzzy_dedupe(items, threshold=0.9, ignore_case=True):
    from je_auto_control.utils.fuzzy import fuzzy_dedupe as _dedupe
    return {"unique": _dedupe(items, threshold=threshold,
                              ignore_case=ignore_case)}


def s3_upload(local_path, key=None):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"key": get_default_store().upload(local_path, key)}


def s3_download(key, local_path):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"path": get_default_store().download(key, local_path)}


def s3_list(prefix=None):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"keys": get_default_store().list(prefix)}


def s3_delete(key):
    from je_auto_control.utils.artifact_store import get_default_store
    return {"deleted": get_default_store().delete(key)}


def image_hash(path, algo="average"):
    from je_auto_control.utils.image_dedup import average_hash, dhash
    hasher = dhash if algo == "dhash" else average_hash
    return {"hash": hasher(path)}


def dedupe_images(paths, max_distance=5):
    from je_auto_control.utils.image_dedup import dedupe_images as _dedupe
    return {"unique": _dedupe(paths, max_distance=max_distance)}


def canonicalize_url(url):
    from je_auto_control.utils.url_canon import canonicalize_url as _canon
    return {"url": _canon(url)}


def normalize_url(url, sort_query=False, drop_fragment=False):
    from je_auto_control.utils.url_canon import normalize_url as _norm
    return {"url": _norm(url, sort_query=bool(sort_query),
                         drop_fragment=bool(drop_fragment))}


def urls_equal(first, second):
    from je_auto_control.utils.url_canon import urls_equal as _equal
    return {"equal": _equal(first, second)}


def parse_decimal(text, locale="en_US"):
    from je_auto_control.utils.locale_parse import parse_decimal as _parse
    return {"value": _parse(text, locale)}


def parse_number(text, locale="en_US"):
    from je_auto_control.utils.locale_parse import parse_number as _parse
    return {"value": _parse(text, locale)}


def format_decimal(value, locale="en_US"):
    from je_auto_control.utils.locale_parse import format_decimal as _fmt
    return {"text": _fmt(value, locale)}


def format_currency(value, currency, locale="en_US"):
    from je_auto_control.utils.locale_parse import format_currency as _fmt
    return {"text": _fmt(value, currency, locale)}


def format_date(value, locale="en_US", fmt="medium"):
    from je_auto_control.utils.locale_parse import format_date as _fmt
    return {"text": _fmt(value, locale, fmt)}


def voice_register(phrase, actions):
    from je_auto_control.utils.voice import default_voice_router
    default_voice_router.register(phrase, actions)
    return {"phrases": default_voice_router.phrases()}


def voice_dispatch(text):
    from je_auto_control.utils.voice import default_voice_router
    outcome = default_voice_router.dispatch(text)
    return {"matched": outcome["matched"], "phrase": outcome["phrase"]}


def voice_list():
    from je_auto_control.utils.voice import default_voice_router
    return {"phrases": default_voice_router.phrases()}


def voice_clear():
    from je_auto_control.utils.voice import default_voice_router
    default_voice_router.clear()
    return {"cleared": True}


def to_physical(x, y, physical_w, physical_h, model_w, model_h):
    from je_auto_control.utils.coordinate_space import CoordinateSpace
    px, py = CoordinateSpace(physical_w, physical_h, model_w,
                             model_h).to_physical(x, y)
    return {"x": px, "y": py}


def to_model(x, y, physical_w, physical_h, model_w, model_h):
    from je_auto_control.utils.coordinate_space import CoordinateSpace
    mx, my = CoordinateSpace(physical_w, physical_h, model_w,
                             model_h).to_model(x, y)
    return {"x": mx, "y": my}


def loop_guard_observe(tool, args=None, result_digest=""):
    from je_auto_control.utils.loop_guard import default_loop_guard
    verdict = default_loop_guard.observe(tool, args, result_digest)
    return {"pattern": verdict.pattern, "level": verdict.level,
            "count": verdict.count}


def loop_guard_reset():
    from je_auto_control.utils.loop_guard import default_loop_guard
    default_loop_guard.reset()
    return {"reset": True}


def mine_actions(actions, min_len=2, max_len=5, min_count=3):
    from je_auto_control.utils.process_mining import mine_action_log
    report = mine_action_log(actions, min_len=min_len, max_len=max_len,
                             min_count=min_count)
    return {
        "total_actions": report.total_actions,
        "patterns": [{"actions": list(p.actions), "count": p.count}
                     for p in report.patterns],
        "candidates": [{"actions": list(c.pattern.actions),
                        "count": c.pattern.count, "score": c.score}
                       for c in report.candidates],
    }


def set_asset(name, value, asset_type="text", environment="default", db=None):
    from je_auto_control.utils.assets.assets import store_set
    return store_set(name, value, asset_type=asset_type,
                     environment=environment, db=db)


def get_asset(name, environment="default", db=None):
    from je_auto_control.utils.assets.assets import store_get
    return store_get(name, environment=environment, db=db)


def list_assets(environment=None, db=None):
    from je_auto_control.utils.assets.assets import store_list
    return store_list(environment=environment, db=db)


def emit_event(event_type, data=None, source="je_auto_control",
               subject=None, url=None):
    from je_auto_control.utils.events import post_cloudevent, to_cloudevent
    event = to_cloudevent(event_type, source, data, subject=subject)
    result = {"event": event}
    if url:
        result["status"] = post_cloudevent(url, event)
    return result


def notify_webhook(url, text, transport="raw", title=None):
    from je_auto_control.utils.notify_channels import (
        notify_webhook as _notify)
    outcome = _notify(url, text, transport=transport, title=title)
    return {"ok": outcome.ok, "status": outcome.status,
            "transport": outcome.transport}


def json_query(data, path):
    from je_auto_control.utils.jsonpath import json_query as _q
    return {"matches": _q(data, path)}


def json_extract(data, mapping):
    from je_auto_control.utils.jsonpath import json_extract as _x
    return {"result": _x(data, mapping)}


def validate_json(data, schema):
    from je_auto_control.utils.json_schema import validate_json as _v
    return _v(data, schema).to_dict()


def scan_vulns(components, advisories=None):
    from je_auto_control.utils.vuln_scan import scan_components
    if isinstance(components, dict):
        components = components.get("components", [])
    findings = scan_components(components, advisories or [])
    return {"findings": findings, "count": len(findings)}


def apply_vex(findings, vex):
    from je_auto_control.utils.vex import apply_vex as _apply
    kept = _apply(findings, vex)
    return {"findings": kept, "count": len(kept)}


def check_licenses(components, allow=None, deny=None):
    from je_auto_control.utils.license_policy import evaluate_sbom
    if isinstance(components, dict):
        components = components.get("components", [])
    violations = evaluate_sbom(components, allow=allow, deny=deny)
    return {"violations": violations, "count": len(violations)}


def jwt_encode(claims, key, alg="HS256"):
    from je_auto_control.utils.jwt import encode_jwt
    return {"token": encode_jwt(claims, key, alg=alg)}


def jwt_decode(token, key, algorithms=None, audience=None, leeway=0.0):
    from je_auto_control.utils.jwt import ClaimsPolicy, JwtError, decode_jwt
    policy = ClaimsPolicy(algorithms=tuple(algorithms) if algorithms
                          else ("HS256",), audience=audience, leeway=leeway)
    try:
        claims = decode_jwt(token, key, policy)
    except JwtError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "claims": claims}


_RATE_LIMITERS = {}
_RATE_LIMITERS_LOCK = threading.Lock()


def rate_limit(name, rate=1.0, capacity=1.0, n=1.0):
    from je_auto_control.utils.rate_limit import TokenBucket
    rate = float(rate)
    capacity = float(capacity)
    with _RATE_LIMITERS_LOCK:
        existing = _RATE_LIMITERS.get(name)
        # setdefault silently ignored a changed rate/capacity for a reused
        # name; rebuild the bucket when either parameter differs so the caller
        # actually gets the limit they asked for.
        if existing is None or existing[0] != rate or existing[1] != capacity:
            bucket = TokenBucket(rate, capacity)
            _RATE_LIMITERS[name] = (rate, capacity, bucket)
        else:
            bucket = existing[2]
    acquired = bucket.try_acquire(float(n))
    return {"acquired": acquired, "tokens": round(bucket.tokens, 4),
            "wait": round(bucket.time_until_available(float(n)), 4)}


def resolve_pointer(doc, pointer):
    from je_auto_control.utils.json_patch import resolve_pointer as _resolve
    return {"value": _resolve(doc, pointer)}


def apply_json_patch(doc, patch):
    from je_auto_control.utils.json_patch import apply_patch
    return {"result": apply_patch(doc, patch)}


def make_json_patch(old, new):
    from je_auto_control.utils.json_patch import make_patch
    return {"patch": make_patch(old, new)}


def merge_patch(doc, patch):
    from je_auto_control.utils.json_patch import merge_patch as _merge
    return {"result": _merge(doc, patch)}


def search_documents(docs, query, top_k=10, mode="bm25"):
    from je_auto_control.utils.search_index import search_documents as _search
    hits = _search(docs, query, top_k=int(top_k), mode=mode)
    return {"hits": [{"doc_id": h.doc_id, "score": h.score} for h in hits]}


def describe_stats(values):
    from je_auto_control.utils.stats import describe
    return describe(values)


def ab_significance(a_conv, a_n, b_conv, b_n):
    from je_auto_control.utils.stats import two_proportion_z_test
    return two_proportion_z_test(int(a_conv), int(a_n), int(b_conv), int(b_n))


def rrule_occurrences(rule, dtstart, count=10):
    import datetime as _dt
    from je_auto_control.utils.recurrence import occurrences, parse_rrule
    start = _dt.datetime.fromisoformat(dtstart)
    moments = occurrences(parse_rrule(rule), start, count=int(count))
    return {"occurrences": [moment.isoformat() for moment in moments]}


def rrule_next(rule, dtstart, now=None):
    import datetime as _dt
    from je_auto_control.utils.recurrence import next_occurrence, parse_rrule
    start = _dt.datetime.fromisoformat(dtstart)
    when = _dt.datetime.fromisoformat(now) if now else None
    moment = next_occurrence(parse_rrule(rule), start, now=when)
    return {"next": moment.isoformat() if moment else None}


def match_json(actual, expected, partial=False, match_type=False):
    from je_auto_control.utils.json_contract import match_json as _match
    return _match(actual, expected, partial=bool(partial),
                  match_type=bool(match_type)).to_dict()


def diff_json(actual, expected):
    from je_auto_control.utils.json_contract import diff_json as _diff
    return {"diffs": _diff(actual, expected)}


def run_chaos(spec):
    from je_auto_control.utils.executor.action_executor import _run_chaos
    return _run_chaos(spec)


def evaluate_slo(records, target, window_s=None):
    from je_auto_control.utils.slo import evaluate_slo as _slo
    return _slo(records, float(target), window_s=window_s)


def burn_alerts(records, target):
    from je_auto_control.utils.slo import burn_alerts as _alerts
    alerts = _alerts(records, float(target))
    return {"alerts": alerts, "firing": bool(alerts)}


def percentiles(samples, qs=None):
    from je_auto_control.utils.percentiles import exact_percentiles
    result = exact_percentiles(samples, qs=tuple(qs) if qs else (50, 90, 95, 99))
    return {"percentiles": {str(q): value for q, value in result.items()}}


def bulkhead_run(name, max_concurrent, actions):
    from je_auto_control.utils.executor.action_executor import _bulkhead_run
    return _bulkhead_run(name, max_concurrent, actions)


def retry_after(response):
    from je_auto_control.utils.bulkhead import next_delay
    return {"delay": next_delay(response)}


def http_replay(cassette, url, method="GET"):
    from je_auto_control.utils.http_cassette import Cassette
    interactions = (cassette.get("interactions", [])
                    if isinstance(cassette, dict) else cassette)
    response = Cassette(interactions).replay(
        {"method": str(method).upper(), "url": url})
    return {"response": response}


def trace_inject(headers=None, traceparent=None):
    from je_auto_control.utils.executor.action_executor import _trace_inject
    return _trace_inject(headers, traceparent)


def trace_extract(headers):
    from je_auto_control.utils.executor.action_executor import _trace_extract
    return _trace_extract(headers)


def baggage_parse(header):
    from je_auto_control.utils.executor.action_executor import _baggage_parse
    return _baggage_parse(header)


def baggage_format(items):
    from je_auto_control.utils.executor.action_executor import _baggage_format
    return _baggage_format(items)


def normalize_text(text, form="NFKC", casefold=True, collapse_ws=True):
    from je_auto_control.utils.executor.action_executor import _normalize_text
    return _normalize_text(text, form, casefold, collapse_ws)


def slugify(text, sep="-"):
    from je_auto_control.utils.executor.action_executor import _slugify
    return _slugify(text, sep)


def text_similarity(a, b, metric="jaro_winkler"):
    from je_auto_control.utils.executor.action_executor import _text_similarity
    return _text_similarity(a, b, metric)


def simhash(text, bits=64):
    from je_auto_control.utils.executor.action_executor import _simhash
    return _simhash(text, bits)


def near_duplicates(texts, max_distance=3):
    from je_auto_control.utils.executor.action_executor import _near_duplicates
    return _near_duplicates(texts, max_distance)


def canonical_log(fields):
    from je_auto_control.utils.executor.action_executor import _canonical_log
    return _canonical_log(fields)


def spans_to_otlp(spans, resource_attrs=None):
    from je_auto_control.utils.executor.action_executor import _spans_to_otlp
    return _spans_to_otlp(spans, resource_attrs)


def validate_config(schema, config):
    from je_auto_control.utils.executor.action_executor import _validate_config
    return _validate_config(schema, config)


def resolve_ref(ref):
    from je_auto_control.utils.executor.action_executor import _resolve_ref
    return _resolve_ref(ref)


def resolve_refs(obj):
    from je_auto_control.utils.executor.action_executor import _resolve_refs
    return _resolve_refs(obj)


def parse_link_header(value):
    from je_auto_control.utils.executor.action_executor import _parse_link_header
    return _parse_link_header(value)


def next_url(value):
    from je_auto_control.utils.executor.action_executor import _next_url
    return _next_url(value)


def build_multipart(fields=None, files=None, boundary=None):
    from je_auto_control.utils.executor.action_executor import _build_multipart
    return _build_multipart(fields, files, boundary)


def parse_multipart(content_type, body_base64):
    from je_auto_control.utils.executor.action_executor import _parse_multipart
    return _parse_multipart(content_type, body_base64)


def decode_body(headers, body_base64):
    from je_auto_control.utils.executor.action_executor import _decode_body
    return _decode_body(headers, body_base64)


def parse_quality_values(header):
    from je_auto_control.utils.executor.action_executor import (
        _parse_quality_values)
    return _parse_quality_values(header)


def cookie_header(set_cookies):
    from je_auto_control.utils.executor.action_executor import _cookie_header
    return _cookie_header(set_cookies)


def parse_set_cookie(header):
    from je_auto_control.utils.executor.action_executor import _parse_set_cookie
    return _parse_set_cookie(header)


def parse_cache_control(headers):
    from je_auto_control.utils.executor.action_executor import (
        _parse_cache_control)
    return _parse_cache_control(headers)


def store_validators(response):
    from je_auto_control.utils.executor.action_executor import _store_validators
    return _store_validators(response)


def redact_config(obj, mask="***"):
    from je_auto_control.utils.executor.action_executor import _redact_config
    return _redact_config(obj, mask)


def redact_secret_text(text, mask="***"):
    from je_auto_control.utils.executor.action_executor import (
        _redact_secret_text)
    return _redact_secret_text(text, mask)


def profile_rows(rows, columns=None):
    from je_auto_control.utils.executor.action_executor import _profile_rows
    return _profile_rows(rows, columns)


def infer_schema(rows, columns=None):
    from je_auto_control.utils.executor.action_executor import _infer_schema
    return _infer_schema(rows, columns)


def parse_problem(response):
    from je_auto_control.utils.executor.action_executor import _parse_problem
    return _parse_problem(response)


def parse_dotenv(text):
    from je_auto_control.utils.executor.action_executor import _parse_dotenv
    return _parse_dotenv(text)


def load_dotenv(path, override=False):
    from je_auto_control.utils.executor.action_executor import _load_dotenv
    return _load_dotenv(path, override)


def parse_sse(text):
    from je_auto_control.utils.executor.action_executor import _parse_sse
    return _parse_sse(text)


def resolve_config(layers):
    from je_auto_control.utils.executor.action_executor import _resolve_config
    return _resolve_config(layers)


def explain_config(layers, key):
    from je_auto_control.utils.executor.action_executor import _explain_config
    return _explain_config(layers, key)


def check_compatibility(old, new, mode="backward"):
    from je_auto_control.utils.executor.action_executor import (
        _check_compatibility)
    return _check_compatibility(old, new, mode)


def ts_rate(series, window_s=None):
    from je_auto_control.utils.executor.action_executor import _ts_rate
    return _ts_rate(series, window_s)


def ts_downsample(series, bucket_s, agg="avg"):
    from je_auto_control.utils.executor.action_executor import _ts_downsample
    return _ts_downsample(series, bucket_s, agg)


def detect_anomalies(values, method="mad", threshold=None):
    from je_auto_control.utils.executor.action_executor import _detect_anomalies
    return _detect_anomalies(values, method, threshold)


def sma(values, window):
    from je_auto_control.utils.executor.action_executor import _sma
    return _sma(values, window)


def ewma(values, alpha=0.3):
    from je_auto_control.utils.executor.action_executor import _ewma
    return _ewma(values, alpha)


def idempotency_begin(name, key, request=None):
    from je_auto_control.utils.executor.action_executor import (
        _idempotency_begin)
    return _idempotency_begin(name, key, request)


def idempotency_complete(name, key, response):
    from je_auto_control.utils.executor.action_executor import (
        _idempotency_complete)
    return _idempotency_complete(name, key, response)


def dedup_check(name, message_id, ttl_s=3600):
    from je_auto_control.utils.executor.action_executor import _dedup_check
    return _dedup_check(name, message_id, ttl_s)


def sequence_observe(name, stream_id, seq):
    from je_auto_control.utils.executor.action_executor import _sequence_observe
    return _sequence_observe(name, stream_id, seq)


def cas_put(name, key, value, expected_version=None):
    from je_auto_control.utils.executor.action_executor import _cas_put
    return _cas_put(name, key, value, expected_version)


def cas_get(name, key):
    from je_auto_control.utils.executor.action_executor import _cas_get
    return _cas_get(name, key)


def outbox_enqueue(name, event):
    from je_auto_control.utils.executor.action_executor import _outbox_enqueue
    return _outbox_enqueue(name, event)


def outbox_pending(name):
    from je_auto_control.utils.executor.action_executor import _outbox_pending
    return _outbox_pending(name)


def collation_sort(items, strength="tertiary", tailoring=None, reverse=False):
    from je_auto_control.utils.executor.action_executor import _collation_sort
    return _collation_sort(items, strength, tailoring, reverse)


def collation_compare(first, second, strength="tertiary", tailoring=None):
    from je_auto_control.utils.executor.action_executor import _collation_compare
    return _collation_compare(first, second, strength, tailoring)


def confusable_scan(text):
    from je_auto_control.utils.executor.action_executor import _confusable_scan
    return _confusable_scan(text)


def confusable_compare(first, second):
    from je_auto_control.utils.executor.action_executor import _confusable_compare
    return _confusable_compare(first, second)


def readability_report(text):
    from je_auto_control.utils.executor.action_executor import _readability_report
    return _readability_report(text)


def bidi_check(text):
    from je_auto_control.utils.executor.action_executor import _bidi_check
    return _bidi_check(text)


def bidi_strip(text):
    from je_auto_control.utils.executor.action_executor import _bidi_strip
    return _bidi_strip(text)


def format_list(items, style="and", locale="en"):
    from je_auto_control.utils.executor.action_executor import _format_list
    return _format_list(items, style, locale)


def format_message(pattern, args=None, locale="en"):
    from je_auto_control.utils.executor.action_executor import _format_message
    return _format_message(pattern, args, locale)


def gettext_translate(po, msgid, context=None):
    from je_auto_control.utils.executor.action_executor import _gettext_translate
    return _gettext_translate(po, msgid, context)


def gettext_ngettext(po, msgid, msgid_plural, n):
    from je_auto_control.utils.executor.action_executor import _gettext_ngettext
    return _gettext_ngettext(po, msgid, msgid_plural, n)


def checksum_validate(scheme, number):
    from je_auto_control.utils.executor.action_executor import _checksum_validate
    return _checksum_validate(scheme, number)


def checksum_digit(scheme, partial):
    from je_auto_control.utils.executor.action_executor import _checksum_digit
    return _checksum_digit(scheme, partial)


def move_along_path(waypoints, easing="linear", per_segment_steps=20):
    from je_auto_control.utils.executor.action_executor import _move_along_path
    return _move_along_path(waypoints, easing, per_segment_steps)


def drag_path(waypoints, button="mouse_left", easing="linear",
              per_segment_steps=20):
    from je_auto_control.utils.executor.action_executor import _drag_path
    return _drag_path(waypoints, button, easing, per_segment_steps)


def set_field_text(text, clear="select_all", paste=False, modifier="ctrl"):
    from je_auto_control.utils.executor.action_executor import _set_field_text
    return _set_field_text(text, clear, paste, modifier)


def hold_key(key, duration_s=1.0, rate_hz=None):
    from je_auto_control.utils.executor.action_executor import _hold_key
    return _hold_key(key, duration_s, rate_hz)


def move_mouse_relative(dx, dy):
    from je_auto_control.utils.executor.action_executor import _move_mouse_relative
    return _move_mouse_relative(dx, dy)


def input_reachable():
    from je_auto_control.utils.executor.action_executor import (
        _input_reachable,
    )
    return _input_reachable()


def type_unicode(text, modifier="ctrl"):
    from je_auto_control.utils.executor.action_executor import _type_unicode
    return _type_unicode(text, modifier)


def type_unicode_keys(text):
    from je_auto_control.utils.executor.action_executor import _type_unicode_keys
    return _type_unicode_keys(text)


def type_unicode_text(text, modifier="ctrl"):
    from je_auto_control.utils.executor.action_executor import _type_unicode_text
    return _type_unicode_text(text, modifier)


def with_modifiers(modifiers, actions):
    from je_auto_control.utils.executor.action_executor import _with_modifiers
    return _with_modifiers(modifiers, actions)


def grid_cell(boxes, row, col, row_tolerance=10):
    from je_auto_control.utils.executor.action_executor import _grid_cell
    return _grid_cell(boxes, row, col, row_tolerance)


def match_template(template, min_score=0.8, scales=None, region=None,
                   method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_template
    return _match_template(template, min_score, scales, region, method)


def match_template_all(template, min_score=0.8, max_results=20, nms_iou=0.3,
                       region=None):
    from je_auto_control.utils.executor.action_executor import (
        _match_template_all)
    return _match_template_all(template, min_score, max_results, nms_iou, region)


def match_masked(template, mask=None, min_score=0.9, region=None):
    from je_auto_control.utils.executor.action_executor import _match_masked
    return _match_masked(template, mask, min_score, region)


def match_masked_all(template, mask=None, min_score=0.9, max_results=20,
                     nms_iou=0.3, region=None):
    from je_auto_control.utils.executor.action_executor import (
        _match_masked_all)
    return _match_masked_all(template, mask, min_score, max_results, nms_iou,
                             region)


def match_rotated(template, min_score=0.8, scales=None, angles=None,
                  region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_rotated
    return _match_rotated(template, min_score, scales, angles, region, method)


def match_rotated_all(template, min_score=0.8, scales=None, angles=None,
                      max_results=20, nms_iou=0.3, region=None):
    from je_auto_control.utils.executor.action_executor import (
        _match_rotated_all)
    return _match_rotated_all(template, min_score, scales, angles, max_results,
                              nms_iou, region)


def match_with_trust(template, min_score=0.0, scales=None, ambiguous_ratio=0.9,
                     region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_with_trust
    return _match_with_trust(template, min_score, scales, ambiguous_ratio,
                             region, method)


def auto_threshold(template, region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _auto_threshold
    return _auto_threshold(template, region, method)


def match_auto(template, floor=0.5, max_results=20, region=None,
               method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_auto
    return _match_auto(template, floor, max_results, region, method)


def edge_match(template, min_score=0.7, scales=None, region=None):
    from je_auto_control.utils.executor.action_executor import _edge_match
    return _edge_match(template, min_score, scales, region)


def edge_match_all(template, min_score=0.7, max_results=20, nms_iou=0.3,
                   region=None):
    from je_auto_control.utils.executor.action_executor import _edge_match_all
    return _edge_match_all(template, min_score, max_results, nms_iou, region)


def match_subpixel(template, min_score=0.0, region=None, method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _match_subpixel
    return _match_subpixel(template, min_score, region, method)


def vote_centers(centers, agree_px=10, min_votes=2):
    from je_auto_control.utils.executor.action_executor import _vote_centers
    return _vote_centers(centers, agree_px, min_votes)


def match_ensemble(templates, min_score=0.8, agree_px=10, min_votes=2, region=None):
    from je_auto_control.utils.executor.action_executor import _match_ensemble
    return _match_ensemble(templates, min_score, agree_px, min_votes, region)


def match_color(template, channels=None, min_score=0.7, scales=None, region=None):
    from je_auto_control.utils.executor.action_executor import _match_color
    return _match_color(template, channels, min_score, scales, region)


def match_color_all(template, channels=None, min_score=0.7, max_results=20,
                    nms_iou=0.3, region=None):
    from je_auto_control.utils.executor.action_executor import _match_color_all
    return _match_color_all(template, channels, min_score, max_results, nms_iou,
                            region)


def region_stability(frames, settle_threshold=0.99):
    from je_auto_control.utils.executor.action_executor import _region_stability
    return _region_stability(frames, settle_threshold)


def match_persistence(template, frames, min_score=0.8, agree_px=8):
    from je_auto_control.utils.executor.action_executor import _match_persistence
    return _match_persistence(template, frames, min_score, agree_px)


def grid_cells(rows, cols, region=None):
    from je_auto_control.utils.executor.action_executor import _grid_cells
    return _grid_cells(rows, cols, region)


def cell_for_point(x, y, rows, cols, region=None):
    from je_auto_control.utils.executor.action_executor import _cell_for_point
    return _cell_for_point(x, y, rows, cols, region)


def point_for_cell(label, rows, cols, region=None):
    from je_auto_control.utils.executor.action_executor import _point_for_cell
    return _point_for_cell(label, rows, cols, region)


def populate_table(grid, text_boxes, overlap=0.4):
    from je_auto_control.utils.executor.action_executor import _populate_table
    return _populate_table(grid, text_boxes, overlap)


def column_gutters(boxes, page_width=None, min_gap=8):
    from je_auto_control.utils.executor.action_executor import _column_gutters
    return _column_gutters(boxes, page_width, min_gap)


def detect_borderless_table(boxes, page_width=None, min_gap=8, min_cols=2,
                            min_rows=2):
    from je_auto_control.utils.executor.action_executor import (
        _detect_borderless_table)
    return _detect_borderless_table(boxes, page_width, min_gap, min_cols, min_rows)


def associate_fields(text_boxes, directions=None, max_gap=150):
    from je_auto_control.utils.executor.action_executor import _associate_fields
    return _associate_fields(text_boxes, directions, max_gap)


def match_labels_to_widgets(labels, widgets):
    from je_auto_control.utils.executor.action_executor import (
        _match_labels_to_widgets)
    return _match_labels_to_widgets(labels, widgets)


def flow_order(boxes, min_gap=12):
    from je_auto_control.utils.executor.action_executor import _flow_order
    return _flow_order(boxes, min_gap)


def xy_cut(boxes, min_gap=12):
    from je_auto_control.utils.executor.action_executor import _xy_cut
    return _xy_cut(boxes, min_gap)


def group_paragraphs(lines, line_gap_factor=1.6):
    from je_auto_control.utils.executor.action_executor import _group_paragraphs
    return _group_paragraphs(lines, line_gap_factor)


def detect_lists(lines):
    from je_auto_control.utils.executor.action_executor import _detect_lists
    return _detect_lists(lines)


def classify_lines(lines, heading_ratio=1.2):
    from je_auto_control.utils.executor.action_executor import _classify_lines
    return _classify_lines(lines, heading_ratio)


def outline(lines, heading_ratio=1.2):
    from je_auto_control.utils.executor.action_executor import _outline
    return _outline(lines, heading_ratio)


def find_color_region(rgb, tolerance=20, min_area=50, region=None):
    from je_auto_control.utils.executor.action_executor import (
        _find_color_region)
    return _find_color_region(rgb, tolerance, min_area, region)


def ssim_compare(reference, current=None, ignore=None, region=None):
    from je_auto_control.utils.executor.action_executor import _ssim_compare
    return _ssim_compare(reference, current, ignore, region)


def ssim_changed_regions(reference, current=None, ignore=None, threshold=0.35,
                         min_area=50, region=None):
    from je_auto_control.utils.executor.action_executor import (
        _ssim_changed_regions)
    return _ssim_changed_regions(reference, current, ignore, threshold, min_area,
                                 region)


def feature_match(template, region=None, max_features=500, ratio=0.75,
                  min_inliers=10):
    from je_auto_control.utils.executor.action_executor import _feature_match
    return _feature_match(template, region, max_features, ratio, min_inliers)


def find_shapes(region=None, min_area=400, max_area=None):
    from je_auto_control.utils.executor.action_executor import _find_shapes
    return _find_shapes(region, min_area, max_area)


def find_rectangles(region=None, min_area=400, max_area=None, aspect_range=None,
                    epsilon=0.04):
    from je_auto_control.utils.executor.action_executor import _find_rectangles
    return _find_rectangles(region, min_area, max_area, aspect_range, epsilon)


def tile_rect(slot, screen=None, gap=0):
    from je_auto_control.utils.executor.action_executor import _tile_rect
    return _tile_rect(slot, screen, gap)


def grid_rects(rows, cols, screen=None, gap=0):
    from je_auto_control.utils.executor.action_executor import _grid_rects
    return _grid_rects(rows, cols, screen, gap)


def cascade_rects(count, screen=None, offset=30, size=None):
    from je_auto_control.utils.executor.action_executor import _cascade_rects
    return _cascade_rects(count, screen, offset, size)


def arrange_grid(titles, rows=None, cols=None, gap=0):
    from je_auto_control.utils.executor.action_executor import _arrange_grid
    return _arrange_grid(titles, rows, cols, gap)


def arrange_cascade(titles, offset=30):
    from je_auto_control.utils.executor.action_executor import _arrange_cascade
    return _arrange_cascade(titles, offset)


def preprocess_image(output_path, source=None, steps=None, scale=2.0, region=None,
                     block_size=31, c=11):
    from je_auto_control.utils.executor.action_executor import _preprocess_image
    return _preprocess_image(output_path, source, steps, scale, region,
                             block_size, c)


def enumerate_monitors():
    from je_auto_control.utils.executor.action_executor import _enumerate_monitors
    return _enumerate_monitors()


def monitor_at_point(x, y):
    from je_auto_control.utils.executor.action_executor import _monitor_at_point
    return _monitor_at_point(x, y)


def wait_actionable(template, timeout_s=5.0, stable_for_s=0.3, min_score=0.8,
                    region=None):
    from je_auto_control.utils.executor.action_executor import _wait_actionable
    return _wait_actionable(template, timeout_s, stable_for_s, min_score, region)


def fuse_elements(ocr=None, icon=None, a11y=None, iou_threshold=0.9):
    from je_auto_control.utils.executor.action_executor import _fuse_elements
    return _fuse_elements(ocr, icon, a11y, iou_threshold)


def reading_order(elements, row_tol=12):
    from je_auto_control.utils.executor.action_executor import _reading_order
    return _reading_order(elements, row_tol)


def segment_hsv(lower_hsv, upper_hsv, min_area=50, region=None):
    from je_auto_control.utils.executor.action_executor import _segment_hsv
    return _segment_hsv(lower_hsv, upper_hsv, min_area, region)


def dominant_hue_regions(hue, hue_tol=10, sat_min=80, val_min=80, min_area=50,
                         region=None):
    from je_auto_control.utils.executor.action_executor import (
        _dominant_hue_regions)
    return _dominant_hue_regions(hue, hue_tol, sat_min, val_min, min_area, region)


def find_text_regions(min_area=60, max_area=None, merge=True, max_aspect=12.0,
                      region=None):
    from je_auto_control.utils.executor.action_executor import _find_text_regions
    return _find_text_regions(min_area, max_area, merge, max_aspect, region)


def find_text_lines(y_tolerance=8, region=None):
    from je_auto_control.utils.executor.action_executor import _find_text_lines
    return _find_text_lines(y_tolerance, region)


def find_lines(min_length=80, max_gap=10, orientation="any", region=None):
    from je_auto_control.utils.executor.action_executor import _find_lines
    return _find_lines(min_length, max_gap, orientation, region)


def find_grid(min_length=120, tol=10, region=None):
    from je_auto_control.utils.executor.action_executor import _find_grid
    return _find_grid(min_length, tol, region)


def find_separators(axis="horizontal", min_length=120, tol=10, region=None):
    from je_auto_control.utils.executor.action_executor import _find_separators
    return _find_separators(axis, min_length, tol, region)


def expect_poll(action, key=None, op="truthy", expected=None, timeout_s=5.0,
                interval_s=0.25):
    from je_auto_control.utils.executor.action_executor import _expect_poll
    return _expect_poll(action, key, op, expected, timeout_s, interval_s)


def locate_chain(boxes, ops=None):
    from je_auto_control.utils.executor.action_executor import _locate_chain
    return _locate_chain(boxes, ops)


def set_clipboard_html(html, fragment_plaintext=None):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_html
    return _set_clipboard_html(html, fragment_plaintext)


def get_clipboard_html():
    from je_auto_control.utils.executor.action_executor import _get_clipboard_html
    return _get_clipboard_html()


def set_clipboard_files(paths):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_files
    return _set_clipboard_files(paths)


def get_clipboard_files():
    from je_auto_control.utils.executor.action_executor import _get_clipboard_files
    return _get_clipboard_files()


def set_clipboard_rtf(text):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_rtf
    return _set_clipboard_rtf(text)


def get_clipboard_rtf():
    from je_auto_control.utils.executor.action_executor import _get_clipboard_rtf
    return _get_clipboard_rtf()


def set_clipboard_csv(rows, delimiter=","):
    from je_auto_control.utils.executor.action_executor import _set_clipboard_csv
    return _set_clipboard_csv(rows, delimiter)


def get_clipboard_csv(delimiter=","):
    from je_auto_control.utils.executor.action_executor import _get_clipboard_csv
    return _get_clipboard_csv(delimiter)


def clipboard_formats():
    from je_auto_control.utils.executor.action_executor import _clipboard_formats
    return _clipboard_formats()


def classify_formats(formats):
    from je_auto_control.utils.executor.action_executor import _classify_formats
    return _classify_formats(formats)


def diff_formats(before, after):
    from je_auto_control.utils.executor.action_executor import _diff_formats
    return _diff_formats(before, after)


def plan_file_drop(paths, point=None):
    from je_auto_control.utils.executor.action_executor import _plan_file_drop
    return _plan_file_drop(paths, point)


def drop_files(hwnd, paths, point=None):
    from je_auto_control.utils.executor.action_executor import _drop_files
    return _drop_files(hwnd, paths, point)


def image_quality(source=None, region=None):
    from je_auto_control.utils.executor.action_executor import _image_quality
    return _image_quality(source, region)


def quality_gate(source=None, region=None, min_sharpness=100.0,
                 min_contrast=12.0):
    from je_auto_control.utils.executor.action_executor import _quality_gate
    return _quality_gate(source, region, min_sharpness, min_contrast)


def detect_scale(template, haystack=None, region=None, scales=None,
                 method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _detect_scale
    return _detect_scale(template, haystack, region, scales, method)


def scale_sweep(template, haystack=None, region=None, scales=None,
                method="ccoeff_normed"):
    from je_auto_control.utils.executor.action_executor import _scale_sweep
    return _scale_sweep(template, haystack, region, scales, method)


def salient_regions(source=None, region=None, size=64, threshold=None,
                    min_area=4):
    from je_auto_control.utils.executor.action_executor import _salient_regions
    return _salient_regions(source, region, size, threshold, min_area)


def most_salient(source=None, region=None, size=64, threshold=None, min_area=4):
    from je_auto_control.utils.executor.action_executor import _most_salient
    return _most_salient(source, region, size, threshold, min_area)


def failure_signature(error, length=12):
    from je_auto_control.utils.executor.action_executor import _failure_signature
    return _failure_signature(error, length)


def group_failures(errors):
    from je_auto_control.utils.executor.action_executor import _group_failures
    return _group_failures(errors)


def diff_runs(before, after, key="name", regress_factor=1.5):
    from je_auto_control.utils.executor.action_executor import _diff_runs
    return _diff_runs(before, after, key, regress_factor)


def failure_clusters(runs, threshold=0.5, min_size=2):
    from je_auto_control.utils.executor.action_executor import _failure_clusters
    return _failure_clusters(runs, threshold, min_size)


def cofailure_pairs(runs, threshold=0.5):
    from je_auto_control.utils.executor.action_executor import _cofailure_pairs
    return _cofailure_pairs(runs, threshold)


def build_timeline(steps):
    from je_auto_control.utils.executor.action_executor import _build_timeline
    return _build_timeline(steps)


def critical_steps(steps, top=3):
    from je_auto_control.utils.executor.action_executor import _critical_steps
    return _critical_steps(steps, top)


def image_histogram(source=None, bins=32, space="hsv", region=None):
    from je_auto_control.utils.executor.action_executor import _image_histogram
    return _image_histogram(source, bins, space, region)


def histogram_changed(reference, current=None, method="correlation",
                      threshold=0.9, space="hsv", region=None):
    from je_auto_control.utils.executor.action_executor import _histogram_changed
    return _histogram_changed(reference, current, method, threshold, space, region)


def changed_regions(before, after=None, threshold=25, min_area=80, blur=5):
    from je_auto_control.utils.executor.action_executor import _changed_regions
    return _changed_regions(before, after, threshold, min_area, blur)


def has_motion(before, after=None, threshold=25, min_area=80):
    from je_auto_control.utils.executor.action_executor import _has_motion
    return _has_motion(before, after, threshold, min_area)


def set_topmost(title, on=True):
    from je_auto_control.utils.executor.action_executor import _set_topmost
    return _set_topmost(title, on)


def bring_to_front(title):
    from je_auto_control.utils.executor.action_executor import _bring_to_front
    return _bring_to_front(title)


def send_to_back(title):
    from je_auto_control.utils.executor.action_executor import _send_to_back
    return _send_to_back(title)


def soft_assert(checks, raise_on_fail=False):
    from je_auto_control.utils.executor.action_executor import _soft_assert
    return _soft_assert(checks, raise_on_fail)


def perceptual_diff(actual, expected, threshold=0.1, include_aa=False,
                    max_diff_ratio=None):
    from je_auto_control.utils.executor.action_executor import _perceptual_diff
    return _perceptual_diff(actual, expected, threshold, include_aa, max_diff_ratio)


def get_client_rect(title):
    from je_auto_control.utils.executor.action_executor import _get_client_rect
    return _get_client_rect(title)


def client_point(title, x, y):
    from je_auto_control.utils.executor.action_executor import _client_point
    return _client_point(title, x, y)


def cua_command(payload, source="canonical"):
    from je_auto_control.utils.executor.action_executor import _cua_command
    return _cua_command(payload, source)


def serialize_observation(elements, viewport=None, max_elements=80):
    from je_auto_control.utils.executor.action_executor import (
        _serialize_observation)
    return _serialize_observation(elements, viewport, max_elements)


def observation_index(elements, viewport=None, max_elements=80):
    from je_auto_control.utils.executor.action_executor import _observation_index
    return _observation_index(elements, viewport, max_elements)


def delta_observation(prev, curr, viewport=None, max_elements=80, max_lines=40,
                      interactive_only=True):
    from je_auto_control.utils.executor.action_executor import _delta_observation
    return _delta_observation(prev, curr, viewport, max_elements, max_lines,
                              interactive_only)


def classify_effect(before, after, action, radius=64):
    from je_auto_control.utils.executor.action_executor import _classify_effect
    return _classify_effect(before, after, action, radius)


def effect_near_point(before, after, point, radius=64):
    from je_auto_control.utils.executor.action_executor import _effect_near_point
    return _effect_near_point(before, after, point, radius)


def check_postcondition(after, spec, before=None):
    from je_auto_control.utils.executor.action_executor import _check_postcondition
    return _check_postcondition(after, spec, before)


def plan_repair(verdict, max_attempts=3):
    from je_auto_control.utils.executor.action_executor import _plan_repair
    return _plan_repair(verdict, max_attempts)


def consensus_point(candidates, cluster_radius=24):
    from je_auto_control.utils.executor.action_executor import _consensus_point
    return _consensus_point(candidates, cluster_radius)


def consensus_element(candidates, elements):
    from je_auto_control.utils.executor.action_executor import _consensus_element
    return _consensus_element(candidates, elements)


def settle_point(churns, quiet_samples=3, max_churn=1.0):
    from je_auto_control.utils.executor.action_executor import _settle_point
    return _settle_point(churns, quiet_samples, max_churn)


def build_critic_record(action, before, after, postcondition=None, radius=64):
    from je_auto_control.utils.executor.action_executor import _build_critic_record
    return _build_critic_record(action, before, after, postcondition, radius)


def score_step(record):
    from je_auto_control.utils.executor.action_executor import _score_step
    return _score_step(record)


def validate_action(action, screen=None, targets=None):
    from je_auto_control.utils.executor.action_executor import _validate_action
    return _validate_action(action, screen, targets)


def replay_trace(trace):
    from je_auto_control.utils.executor.action_executor import _replay_trace
    return _replay_trace(trace)


def match_elements(before, after, iou_threshold=0.5):
    from je_auto_control.utils.executor.action_executor import _match_elements
    return _match_elements(before, after, iou_threshold)


def assign_stable_ids(elements, prior=None, iou_threshold=0.5):
    from je_auto_control.utils.executor.action_executor import _assign_stable_ids
    return _assign_stable_ids(elements, prior, iou_threshold)


def score_candidates(candidates, want_role=None, want_name=None, anchor=None):
    from je_auto_control.utils.executor.action_executor import _score_candidates
    return _score_candidates(candidates, want_role, want_name, anchor)


def best_candidate(candidates, want_role=None, want_name=None, anchor=None):
    from je_auto_control.utils.executor.action_executor import _best_candidate
    return _best_candidate(candidates, want_role, want_name, anchor)


def read_barcodes(source=None, region=None):
    from je_auto_control.utils.executor.action_executor import _read_barcodes
    return _read_barcodes(source, region)


def detect_drift(reference, current, threshold=0.25, bins=10):
    from je_auto_control.utils.executor.action_executor import _detect_drift
    return _detect_drift(reference, current, threshold, bins)


def categorical_drift(reference, current):
    from je_auto_control.utils.executor.action_executor import _categorical_drift
    return _categorical_drift(reference, current)


def diff_rows(old_rows, new_rows, key):
    from je_auto_control.utils.executor.action_executor import _diff_rows
    return _diff_rows(old_rows, new_rows, key)


def cell_changes(old_rows, new_rows, key):
    from je_auto_control.utils.executor.action_executor import _cell_changes
    return _cell_changes(old_rows, new_rows, key)


def check_foreign_key(child_rows, child_col, parent_rows, parent_col):
    from je_auto_control.utils.executor.action_executor import _check_foreign_key
    return _check_foreign_key(child_rows, child_col, parent_rows, parent_col)


def check_unique_key(rows, cols):
    from je_auto_control.utils.executor.action_executor import _check_unique_key
    return _check_unique_key(rows, cols)


def check_accepted_values(rows, col, allowed):
    from je_auto_control.utils.executor.action_executor import (
        _check_accepted_values)
    return _check_accepted_values(rows, col, allowed)


def check_row_count(rows, minimum=None, maximum=None):
    from je_auto_control.utils.executor.action_executor import _check_row_count
    return _check_row_count(rows, minimum, maximum)


def build_provenance(paths, builder_id="je_auto_control"):
    from je_auto_control.utils.provenance import build_provenance, subject_for
    subjects = [subject_for(path) for path in paths]
    return {"statement": build_provenance(subjects, builder_id=builder_id)}


def verify_provenance(statement, files):
    from je_auto_control.utils.provenance import verify_provenance as _verify
    mismatches = _verify(statement, files)
    return {"ok": not mismatches, "mismatches": mismatches}


def evaluate_flag(flags, key, context=None):
    from je_auto_control.utils.feature_flags import (
        FlagStore, evaluate_flag as _ev)
    store = FlagStore.from_dict(flags) if isinstance(flags, dict) else flags
    return _ev(store, key, context or {})


def flag_enabled(flags, key, context=None, default=False):
    from je_auto_control.utils.feature_flags import FlagStore, is_enabled
    store = FlagStore.from_dict(flags) if isinstance(flags, dict) else flags
    return {"enabled": is_enabled(store, key, context or {}, bool(default))}


def unified_diff(a, b):
    from je_auto_control.utils.text_diff import unified_diff as _diff
    return {"diff": _diff(a, b)}


def apply_unified(text, diff):
    from je_auto_control.utils.text_diff import apply_unified as _apply
    return {"result": _apply(text, diff)}


def three_way_merge(base, ours, theirs):
    from je_auto_control.utils.text_diff import three_way_merge as _merge
    outcome = _merge(base, ours, theirs)
    return {"text": outcome.text, "clean": outcome.clean,
            "conflicts": outcome.conflicts}


def run_saga(steps):
    from je_auto_control.utils.saga import run_saga as _run
    result = _run(steps)
    return {"ok": result.ok, "completed": result.completed,
            "compensated": result.compensated,
            "failed_step": result.failed_step, "error": result.error}


def decision_table(spec, context):
    from je_auto_control.utils.decision_table import evaluate_table
    return {"result": evaluate_table(spec, context)}


def repair_record(key, method, coordinates=None, description=None,
                  confidence=1.0, auto_threshold=0.9, db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    sug = RepairStore(db).record(
        key, method=method, coordinates=coordinates, description=description,
        confidence=confidence, auto_threshold=auto_threshold)
    return {"id": sug.id, "status": sug.status}


def repair_resolved(key, db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    return {"locator": RepairStore(db).resolved(key)}


def repair_pending(db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    return {"pending": RepairStore(db).pending()}


def repair_approve(suggestion_id, db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    return {"approved": RepairStore(db).approve(suggestion_id)}


def detect_pii(text, kinds=None):
    from je_auto_control.utils.pii_text import detect_pii as _detect
    findings = _detect(text, kinds=kinds)
    return {"findings": [{"kind": f.kind, "value": f.value,
                          "start": f.start, "end": f.end} for f in findings]}


def redact_pii(text, kinds=None, mode="label", mask_char="*"):
    from je_auto_control.utils.pii_text import redact_pii_text
    return {"text": redact_pii_text(text, kinds=kinds, mode=mode,
                                    mask_char=mask_char)}


def export_sarif(findings, path=None, tool_name="AutoControl"):
    from je_auto_control.utils.sarif import to_sarif, write_sarif
    result = {"sarif": to_sarif(findings, tool_name=tool_name)}
    if path:
        result["path"] = write_sarif(findings, path, tool_name=tool_name)
    return result


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


def self_heal_locate(template_path: Optional[str] = None,
                     description: Optional[str] = None,
                     detect_threshold: float = 0.9,
                     screen_region: Optional[List[int]] = None,
                     model: Optional[str] = None,
                     raise_on_miss: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.self_healing import self_heal_locate as _impl
    return _impl(
        template_path=template_path, description=description,
        detect_threshold=float(detect_threshold),
        screen_region=screen_region, model=model,
        raise_on_miss=bool(raise_on_miss),
    ).to_dict()


def self_heal_click(template_path: Optional[str] = None,
                    description: Optional[str] = None,
                    mouse_keycode: str = "mouse_left",
                    detect_threshold: float = 0.9,
                    screen_region: Optional[List[int]] = None,
                    model: Optional[str] = None,
                    raise_on_miss: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.self_healing import self_heal_click as _impl
    return _impl(
        template_path=template_path, description=description,
        mouse_keycode=mouse_keycode,
        detect_threshold=float(detect_threshold),
        screen_region=screen_region, model=model,
        raise_on_miss=bool(raise_on_miss),
    ).to_dict()


def self_heal_log_list(limit: int = 50) -> List[Dict[str, Any]]:
    from je_auto_control.utils.self_healing import default_heal_log
    return [event.to_dict()
            for event in default_heal_log.list_events(limit=int(limit))]


def self_heal_log_clear() -> Dict[str, Any]:
    from je_auto_control.utils.self_healing import default_heal_log
    default_heal_log.clear()
    return {"cleared": True, "path": str(default_heal_log.path)}


# === WebRunner bridge (browser automation via je_web_runner) ================

def web_available() -> bool:
    from je_auto_control.utils.webrunner_bridge import is_webrunner_available
    return bool(is_webrunner_available())


def web_list_commands() -> List[str]:
    from je_auto_control.utils.webrunner_bridge import list_webrunner_commands
    return list(list_webrunner_commands())


def web_run(action: Dict[str, Any]) -> Any:
    from je_auto_control.utils.webrunner_bridge import run_webrunner_action
    return run_webrunner_action(action)


def web_run_actions(actions: List[Dict[str, Any]]) -> List[Any]:
    from je_auto_control.utils.webrunner_bridge import run_webrunner_actions
    return list(run_webrunner_actions(actions))


def web_open(url: str, browser: str = "chrome") -> Any:
    from je_auto_control.utils.webrunner_bridge import web_open as _open
    return _open(url, browser=browser)


def web_quit() -> Any:
    from je_auto_control.utils.webrunner_bridge import web_quit as _quit
    return _quit()


def web_screenshot(file_path: str) -> Any:
    from je_auto_control.utils.webrunner_bridge import (
        web_screenshot as _shot,
    )
    return _shot(file_path)


def web_current_url() -> Any:
    from je_auto_control.utils.webrunner_bridge import (
        web_current_url as _url,
    )
    return _url()


def run_dag(definition: Dict[str, Any],
            max_parallel: int = 4) -> Dict[str, Any]:
    from je_auto_control.utils.dag import run_dag as _run_dag
    return _run_dag(definition, max_parallel=int(max_parallel)).to_dict()


def a11y_dump(app_name: Optional[str] = None,
              max_results: int = 500) -> Dict[str, Any]:
    from je_auto_control.utils.accessibility import dump_accessibility_tree
    return dump_accessibility_tree(
        app_name=app_name, max_results=int(max_results),
    ).to_dict()


def walk_tree(app_name=None, max_results: int = 500):
    from je_auto_control.utils.executor.action_executor import _walk_tree
    return _walk_tree(app_name, max_results)


def humanize_role(role):
    from je_auto_control.utils.executor.action_executor import _humanize_role
    return _humanize_role(role)


def tab_order(app_name=None, max_results: int = 500):
    from je_auto_control.utils.executor.action_executor import _tab_order
    return _tab_order(app_name, max_results)


def audit_focus_order(app_name=None, max_results: int = 500):
    from je_auto_control.utils.executor.action_executor import _audit_focus_order
    return _audit_focus_order(app_name, max_results)


def focus_control(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.executor.action_executor import _focus_control
    return _focus_control(name, role, app_name, automation_id)


def a11y_record_start(app_name: Optional[str] = None,
                      poll_interval_s: float = 0.25,
                      min_movement_px: int = 8) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import (
        _a11y_record_start,
    )
    return _a11y_record_start(
        app_name=app_name,
        poll_interval_s=float(poll_interval_s),
        min_movement_px=int(min_movement_px),
    )


def a11y_record_stop() -> List[Dict[str, Any]]:
    from je_auto_control.utils.executor.action_executor import (
        _a11y_record_stop,
    )
    return _a11y_record_stop()


def ab_locate(target_id: str,
              strategies: Dict[str, Dict[str, Any]],
              max_parallel: int = 4,
              record: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_locate as _impl
    from je_auto_control.utils.anchor_locator import (
        Locator as AnchorLocator,
    )
    locators = {name: AnchorLocator(**spec)
                for name, spec in strategies.items()}
    return _impl(
        target_id=target_id, strategies=locators,
        max_parallel=int(max_parallel), record=bool(record),
    ).to_dict()


def ab_report(target_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_report_for
    return ab_report_for(target_id).to_dict()


def ab_best_strategy(target_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_best_strategy as _impl
    return {"target_id": target_id, "strategy": _impl(target_id)}


def failure_hook_fire(source: str, source_id: str,
                       error_text: str = "",
                       script_path: Optional[str] = None,
                       screenshot_path: Optional[str] = None,
                       log_tail: str = "",
                       metadata: Optional[Dict[str, Any]] = None,
                       ) -> List[Dict[str, Any]]:
    from je_auto_control.utils.failure_hooks import (
        FailureReport, default_failure_hook_manager,
    )
    report = FailureReport(
        source=source, source_id=source_id, error_text=error_text,
        script_path=script_path, screenshot_path=screenshot_path,
        log_tail=log_tail, metadata=dict(metadata or {}),
    )
    return [result.to_dict()
            for result in default_failure_hook_manager.fire(report)]


def failure_hook_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.failure_hooks import default_failure_hook_manager
    return default_failure_hook_manager.list_backends()


def costs_record(provider: str, model: str,
                  input_tokens: int, output_tokens: int,
                  label: Optional[str] = None,
                  run_id: Optional[str] = None,
                  user: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.cost_telemetry import record_llm_call
    return record_llm_call(
        provider=provider, model=model,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        label=label, run_id=run_id, user=user,
    ).to_dict()


def costs_summary(limit: int = 10000) -> Dict[str, Any]:
    from je_auto_control.utils.cost_telemetry import (
        default_cost_store, summarise_llm_costs,
    )
    events = default_cost_store.list_events(limit=int(limit))
    return summarise_llm_costs(events).to_dict()


def costs_list(limit: int = 100) -> List[Dict[str, Any]]:
    from je_auto_control.utils.cost_telemetry import default_cost_store
    return [event.to_dict()
            for event in default_cost_store.list_events(limit=int(limit))]


def wait_screen_stable(region: Optional[List[int]] = None,
                        timeout_s: float = 10.0,
                        poll_interval_s: float = 0.2,
                        stable_for_s: float = 0.5,
                        max_pixel_diff: int = 0) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_screen_stable
    return wait_until_screen_stable(
        region=region, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s),
        max_pixel_diff=int(max_pixel_diff),
    ).to_dict()


def wait_image_gone(image, detect_threshold: float = 1.0,
                    timeout_s: float = 10.0, poll_interval_s: float = 0.2,
                    gone_for_s: float = 0.0) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _wait_image_gone
    return _wait_image_gone(image, detect_threshold, timeout_s,
                            poll_interval_s, gone_for_s)


def wait_text_gone(text: str, timeout_s: float = 10.0,
                   poll_interval_s: float = 0.2,
                   gone_for_s: float = 0.0) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _wait_text_gone
    return _wait_text_gone(text, timeout_s, poll_interval_s, gone_for_s)


def wait_color(target_rgb, region=None, tolerance=10, min_fraction=0.5,
               present=True, timeout_s=10.0, poll_interval_s=0.2):
    from je_auto_control.utils.executor.action_executor import _wait_color
    return _wait_color(target_rgb, region, tolerance, min_fraction,
                       present, timeout_s, poll_interval_s)


def wait_window_title(pattern, present=True, regex=True, timeout_s=10.0,
                      poll_interval_s=0.2):
    from je_auto_control.utils.executor.action_executor import _wait_window_title
    return _wait_window_title(pattern, present, regex, timeout_s,
                              poll_interval_s)


def wait_for_file(path: str, timeout_s: float = 30.0,
                  poll_interval_s: float = 0.25,
                  stable_for_s: float = 1.0,
                  min_size: int = 1) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_file
    return wait_until_file(
        path, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s), min_size=int(min_size),
    ).to_dict()


def wait_for_port(host: str, port: int, timeout_s: float = 30.0,
                  poll_interval_s: float = 0.25,
                  connect_timeout_s: float = 1.0) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_port
    return wait_until_port(
        host, int(port), timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        connect_timeout_s=float(connect_timeout_s),
    ).to_dict()


def wait_for_process(name: str, present: bool = True, timeout_s: float = 30.0,
                     poll_interval_s: float = 0.25) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_process
    return wait_until_process(
        name, present=bool(present), timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
    ).to_dict()


def wait_pixel_changes(x: int, y: int,
                        timeout_s: float = 10.0,
                        poll_interval_s: float = 0.1,
                        rgb_tolerance: int = 5) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_pixel_changes
    return wait_until_pixel_changes(
        x=int(x), y=int(y),
        timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        rgb_tolerance=int(rgb_tolerance),
    ).to_dict()


def wait_region_idle(region: List[int],
                      timeout_s: float = 10.0,
                      poll_interval_s: float = 0.2,
                      stable_for_s: float = 0.5,
                      max_pixel_diff: int = 0) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_region_idle
    return wait_until_region_idle(
        region=region, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s),
        max_pixel_diff=int(max_pixel_diff),
    ).to_dict()


def ocr_read_structure(region: Optional[List[int]] = None,
                        lang: str = "eng",
                        min_confidence: float = 60.0,
                        ) -> Dict[str, Any]:
    from je_auto_control.utils.ocr.structure import read_structure
    return read_structure(
        region=region, lang=lang,
        min_confidence=float(min_confidence),
    ).to_dict()


def anchor_locate(anchor: Dict[str, Any], target: Dict[str, Any],
                  relation: str = "near",
                  max_distance_px: float = 200.0,
                  ordinal: int = 1) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _anchor_locate
    return _anchor_locate(anchor, target, relation, max_distance_px, ordinal)


def anchor_locate_all(anchor: Dict[str, Any], target: Dict[str, Any],
                      relation: str = "near",
                      max_distance_px: float = 200.0) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _anchor_locate_all
    return _anchor_locate_all(anchor, target, relation, max_distance_px)


def anchor_click(anchor: Dict[str, Any], target: Dict[str, Any],
                 mouse_keycode: str = "mouse_left",
                 relation: str = "near",
                 max_distance_px: float = 200.0) -> Dict[str, Any]:
    outcome = anchor_locate(anchor, target, relation, max_distance_px)
    if outcome.get("found") and outcome.get("target_coords"):
        cx, cy = outcome["target_coords"]
        from je_auto_control.wrapper.auto_control_mouse import (
            click_mouse, set_mouse_position,
        )
        set_mouse_position(int(cx), int(cy))
        click_mouse(mouse_keycode, int(cx), int(cy))
    return outcome


def chatops_dispatch(message: str,
                     context: Optional[Dict[str, Any]] = None,
                     script_root: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.chatops import (
        CommandRouter, register_chatops_default_commands,
    )
    router = CommandRouter()
    register_chatops_default_commands(router)
    merged: Dict[str, Any] = dict(context or {})
    if script_root is not None:
        merged.setdefault("script_root", script_root)
    result = router.dispatch(message, context=merged)
    return {"matched": False} if result is None else {
        "matched": True, **result.to_dict(),
    }


def presence_register(viewer_id: str, label: str = "",
                      role: str = "observer") -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().register(
        viewer_id, label, role=role,
    ).to_dict()


def presence_unregister(viewer_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return {"viewer_id": viewer_id,
            "removed": default_presence_registry().unregister(viewer_id)}


def presence_update_cursor(viewer_id: str, x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().update_cursor(
        viewer_id, int(x), int(y),
    ).to_dict()


def presence_set_role(viewer_id: str, role: str) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().update_role(viewer_id, role).to_dict()


def presence_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return [row.to_dict() for row in default_presence_registry().list()]


def computer_use(goal: str,
                 display_width_px: Optional[int] = None,
                 display_height_px: Optional[int] = None,
                 display_number: Optional[int] = None,
                 max_steps: int = 25,
                 wall_seconds: float = 300.0,
                 model: str = "claude-opus-4-7",
                 max_tokens: int = 1024) -> Dict[str, Any]:
    from je_auto_control.utils.agent.computer_use import (
        result_to_dict, run_computer_use,
    )
    result = run_computer_use(
        goal,
        display_width_px=display_width_px,
        display_height_px=display_height_px,
        display_number=display_number,
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
        model=model, max_tokens=int(max_tokens),
    )
    return result_to_dict(result)


def run_agent(goal: str,
              backend: str = "anthropic",
              max_steps: int = 25,
              wall_seconds: float = 300.0,
              model: Optional[str] = None,
              max_tokens: int = 1024) -> Dict[str, Any]:
    """Drive the generic plan→act→verify→retry AgentLoop against ``goal``."""
    from je_auto_control.utils.executor.action_executor import _run_agent
    return _run_agent(
        goal=goal, backend=backend,
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
        model=model, max_tokens=int(max_tokens),
    )


def redact_screenshot(file_path: str,
                      output_path: Optional[str] = None,
                      policy: str = "moderate",
                      regions: Optional[List[List[int]]] = None,
                      accessibility: Optional[List[Dict[str, Any]]] = None,
                      ocr: Optional[List[Dict[str, Any]]] = None,
                      ) -> Dict[str, Any]:
    """Blur PII regions in a saved screenshot via the redaction engine."""
    from je_auto_control.utils.executor.action_executor import (
        _redact_screenshot,
    )
    return _redact_screenshot(
        file_path=file_path, output_path=output_path,
        policy=policy, regions=regions,
        accessibility=accessibility, ocr=ocr,
    )


def android_find_element(text: Optional[str] = None,
                         resource_id: Optional[str] = None,
                         description: Optional[str] = None,
                         class_name: Optional[str] = None,
                         timeout_s: float = 5.0,
                         serial: Optional[str] = None,
                         ) -> Dict[str, int]:
    """Find an Android widget via uiautomator2; return its bounding rect."""
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_find_element,
    )
    return _ac_android_find_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=timeout_s, serial=serial,
    )


def android_click_element(text: Optional[str] = None,
                          resource_id: Optional[str] = None,
                          description: Optional[str] = None,
                          class_name: Optional[str] = None,
                          timeout_s: float = 5.0,
                          serial: Optional[str] = None,
                          ) -> Dict[str, int]:
    """Tap the first widget matching the selectors; return click centre."""
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_click_element,
    )
    return _ac_android_click_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=timeout_s, serial=serial,
    )


def android_dump_hierarchy(serial: Optional[str] = None) -> str:
    """Return the device's widget tree as an XML string."""
    from je_auto_control.utils.executor.action_executor import (
        _ac_android_dump_hierarchy,
    )
    return _ac_android_dump_hierarchy(serial=serial)


def ios_tap(x: int, y: int,
            url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.utils.executor.action_executor import _ac_ios_tap
    return _ac_ios_tap(x=int(x), y=int(y), url=url)


def ios_swipe(x1: int, y1: int, x2: int, y2: int,
              duration_s: float = 0.5,
              url: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _ac_ios_swipe
    return _ac_ios_swipe(x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                          duration_s=float(duration_s), url=url)


def ios_type(text: str, url: Optional[str] = None) -> str:
    from je_auto_control.utils.executor.action_executor import _ac_ios_type
    return _ac_ios_type(text=text, url=url)


def ios_screenshot(file_path: str, url: Optional[str] = None) -> str:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_screenshot,
    )
    return _ac_ios_screenshot(file_path=file_path, url=url)


def ios_find_element(name: Optional[str] = None,
                     class_name: Optional[str] = None,
                     predicate: Optional[str] = None,
                     timeout_s: float = 5.0,
                     url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_find_element,
    )
    return _ac_ios_find_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=float(timeout_s), url=url,
    )


def ios_click_element(name: Optional[str] = None,
                      class_name: Optional[str] = None,
                      predicate: Optional[str] = None,
                      timeout_s: float = 5.0,
                      url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_click_element,
    )
    return _ac_ios_click_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=float(timeout_s), url=url,
    )


def ios_dump_source(url: Optional[str] = None) -> str:
    from je_auto_control.utils.executor.action_executor import (
        _ac_ios_dump_source,
    )
    return _ac_ios_dump_source(url=url)


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


# --- USB passthrough — delegate to the shared command module -------------


def usb_passthrough_enable(enabled: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.passthrough_enable(enabled)


def usb_passthrough_status() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.passthrough_status()


def usb_acl_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_list()


def usb_acl_add(vendor_id: str, product_id: str,
                serial: Optional[str] = None, allow: bool = True,
                prompt_on_open: bool = False, label: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_add(
        vendor_id, product_id, serial=serial, allow=allow,
        prompt_on_open=prompt_on_open, label=label,
    )


def usb_acl_remove(vendor_id: str, product_id: str,
                   serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_remove(vendor_id, product_id, serial=serial)


def usb_acl_set_default(policy: str) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_set_default(policy)


def usb_loopback_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.loopback_list()


def usb_loopback_open(vendor_id: str, product_id: str,
                      serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.loopback_open(vendor_id, product_id, serial=serial)


def usb_remote_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.remote_list()


def usb_remote_open(vendor_id: str, product_id: str,
                    serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.remote_open(vendor_id, product_id, serial=serial)


# --- Assertion DSL ---------------------------------------------------------

def assert_text(text: str,
                region: Optional[List[int]] = None,
                lang: str = "eng",
                regex: bool = False,
                present: bool = True,
                ignore_case: bool = True,
                min_confidence: float = 60.0,
                raise_on_fail: bool = True,
                capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_text as _assert
    return _assert(
        text, region=region, lang=lang, regex=bool(regex),
        present=bool(present), ignore_case=bool(ignore_case),
        min_confidence=float(min_confidence),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_image(template_path: str,
                 threshold: float = 0.9,
                 present: bool = True,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_image as _assert
    return _assert(
        template_path, threshold=float(threshold), present=bool(present),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_pixel(x: int, y: int, rgb: List[int],
                 tolerance: int = 0,
                 match: bool = True,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_pixel as _assert
    return _assert(
        int(x), int(y), rgb, tolerance=int(tolerance), match=bool(match),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_window(title: str,
                  exists: bool = True,
                  ignore_case: bool = True,
                  raise_on_fail: bool = True,
                  capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_window as _assert
    return _assert(
        title, exists=bool(exists), ignore_case=bool(ignore_case),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_clipboard(text: str,
                     mode: str = "equals",
                     ignore_case: bool = False,
                     present: bool = True,
                     raise_on_fail: bool = True,
                     capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_clipboard as _assert
    return _assert(
        text, mode=mode, ignore_case=bool(ignore_case),
        present=bool(present), raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_process(name: str,
                   running: bool = True,
                   raise_on_fail: bool = True,
                   capture_on_fail: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_process as _assert
    return _assert(
        name, running=bool(running), raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def assert_file(path: str,
                exists: bool = True,
                contains: Optional[str] = None,
                sha256: Optional[str] = None,
                min_size: Optional[int] = None,
                raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_file as _assert
    return _assert(
        path, exists=bool(exists), contains=contains, sha256=sha256,
        min_size=None if min_size is None else int(min_size),
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def assert_http(url: str,
                status: int = 200,
                contains: Optional[str] = None,
                timeout: float = 10.0,
                method: str = "GET",
                raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_http as _assert
    return _assert(
        url, status=int(status), contains=contains, timeout=float(timeout),
        method=method, raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def assert_all(specs: List[Dict[str, Any]],
               raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_all as _assert
    return _assert(specs, raise_on_fail=bool(raise_on_fail)).to_dict()


def assert_any(specs: List[Dict[str, Any]],
               raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_any as _assert
    return _assert(specs, raise_on_fail=bool(raise_on_fail)).to_dict()


def assert_eventually(spec: Dict[str, Any],
                      timeout: float = 5.0,
                      interval: float = 0.25,
                      raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_eventually as _assert
    return _assert(
        spec, timeout=float(timeout), interval=float(interval),
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


# --- Data-driven execution -------------------------------------------------

def load_data(source: Dict[str, Any],
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
    from je_auto_control.utils.data_source import load_rows
    return load_rows(source, limit=limit if limit is None else int(limit))


# --- Ad-hoc SQL query + assertion ------------------------------------------

def sql_query(database: str, query: str,
              params: Any = None, fetch: str = "all") -> Any:
    from je_auto_control.utils.sql.sql_query import query_sqlite
    return query_sqlite(database, query, params=params, fetch=fetch)


def assert_db(database: str, query: str, params: Any = None,
              op: str = "eq", expected: Any = None,
              raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.assertion import assert_variable
    from je_auto_control.utils.sql.sql_query import query_sqlite
    value = query_sqlite(database, query, params=params, fetch="scalar")
    return assert_variable(
        value, op=op, expected=expected, name="ac_assert_db",
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


# --- PDF text + assertion --------------------------------------------------

def extract_pdf_text(path: str, pages: Any = None) -> str:
    from je_auto_control.utils.pdf.pdf_reader import (
        extract_pdf_text as _extract,
    )
    return _extract(path, pages=pages)


def assert_pdf_text(path: str, text: str, present: bool = True,
                    page: Any = None, case_sensitive: bool = True,
                    raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.pdf.pdf_reader import (
        assert_pdf_text as _assert,
    )
    return _assert(path, text, present=bool(present), page=page,
                   case_sensitive=bool(case_sensitive),
                   raise_on_fail=bool(raise_on_fail))


# --- Send email (SMTP) -----------------------------------------------------

def send_email(message: Dict[str, Any],
               smtp: Dict[str, Any]) -> Dict[str, Any]:
    from je_auto_control.utils.email_send.email_sender import (
        send_email as _send,
    )
    return _send(message, smtp)


# --- HTTP / API request ----------------------------------------------------

def http_request(url: str, method: str = "GET",
                 headers: Optional[Dict[str, Any]] = None,
                 json_body: Any = None, data: Any = None,
                 auth: Optional[Dict[str, Any]] = None,
                 timeout: float = 30.0) -> Dict[str, Any]:
    from je_auto_control.utils.http_client.http_client import (
        http_request as _request,
    )
    return _request(url, method=method, headers=headers, json_body=json_body,
                    data=data, auth=auth, timeout=float(timeout))


# --- Codegen: action list -> source code -----------------------------------

def generate_code(source: Any, target: str = "pytest",
                  name: str = "recorded_flow", style: str = "calls",
                  output: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.codegen.codegen import (
        generate_code as _gen, generate_code_file,
    )
    from je_auto_control.utils.json.json_file import read_action_json
    if output:
        code = generate_code_file(source, output, target=target,
                                  name=name, style=style)
        return {"output": output, "code": code}
    actions = source if isinstance(source, list) else read_action_json(source)
    return {"code": _gen(actions, target=target, name=name, style=style)}


# --- Visual regression + state machine -------------------------------------

def take_golden(path: str, region: Optional[List[int]] = None) -> str:
    from je_auto_control.utils.visual_regression import (
        take_golden as _take,
    )
    return str(_take(path, region=region))


def assert_visual(golden_path: str, region: Optional[List[int]] = None,
                  tolerance: float = 0.0, per_pixel_threshold: int = 16,
                  diff_path: Optional[str] = None,
                  create_if_missing: bool = True,
                  raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import _assert_visual
    return _assert_visual(
        golden_path, region=region, tolerance=tolerance,
        per_pixel_threshold=per_pixel_threshold, diff_path=diff_path,
        create_if_missing=create_if_missing, raise_on_fail=raise_on_fail)


def run_state_machine(spec: Dict[str, Any]) -> Dict[str, Any]:
    from je_auto_control.utils.state_machine import (
        run_state_machine as _run,
    )
    return _run(spec)


# --- Flaky-test detection --------------------------------------------------

def flaky_report(limit: int = 500,
                 min_runs: int = 2,
                 group_by: str = "script_path") -> Dict[str, Any]:
    from je_auto_control.utils.flakiness import analyze_flakiness
    return analyze_flakiness(
        limit=int(limit), min_runs=int(min_runs), group_by=group_by,
    ).to_dict()


# --- QA suite runner + CI reports ------------------------------------------

def run_suite(spec: Dict[str, Any],
              tags: Optional[List[str]] = None,
              respect_quarantine: bool = True,
              junit_path: Optional[str] = None,
              allure_dir: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.test_suite import (
        run_suite as _run, write_allure_results, write_junit_xml,
    )
    result = _run(
        spec, executor=executor, tags=tags,
        respect_quarantine=bool(respect_quarantine),
    )
    payload = result.to_dict()
    reports: Dict[str, Any] = {}
    if junit_path:
        reports["junit"] = write_junit_xml(result, junit_path)
    if allure_dir:
        reports["allure"] = write_allure_results(result, allure_dir)
    if reports:
        payload["reports"] = reports
    return payload


# --- Flaky quarantine ------------------------------------------------------

def quarantine_add(name: str, reason: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return default_quarantine_store().add(name, reason=reason).to_dict()


def quarantine_remove(name: str) -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return {"name": name, "removed": default_quarantine_store().remove(name)}


def quarantine_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return [entry.to_dict() for entry in default_quarantine_store().list()]


def quarantine_auto(flip_rate_threshold: float = 0.5,
                    min_runs: int = 3,
                    limit: int = 500,
                    group_by: str = "script_path") -> List[Dict[str, Any]]:
    from je_auto_control.utils.quarantine import auto_quarantine_from_flakiness
    return [
        entry.to_dict()
        for entry in auto_quarantine_from_flakiness(
            flip_rate_threshold=float(flip_rate_threshold),
            min_runs=int(min_runs), limit=int(limit), group_by=group_by,
        )
    ]


# --- Accessibility / i18n audit --------------------------------------------

def audit_accessibility(app_name: Optional[str] = None,
                        contrast_pairs: Optional[List[Dict[str, Any]]] = None,
                        texts: Optional[List[str]] = None,
                        min_ratio: float = 4.5,
                        max_results: int = 500) -> Dict[str, Any]:
    from je_auto_control.utils.a11y_audit import run_audit
    return run_audit(
        app_name=app_name, contrast_pairs=contrast_pairs, texts=texts,
        min_ratio=float(min_ratio), max_results=int(max_results),
    ).to_dict()


def audit_contrast(foreground: List[int], background: List[int],
                   min_ratio: float = 4.5) -> Dict[str, Any]:
    from je_auto_control.utils.a11y_audit import contrast_ratio
    ratio = contrast_ratio(foreground, background)
    return {
        "ratio": round(ratio, 2),
        "passes_aa": ratio >= float(min_ratio),
        "foreground": list(foreground), "background": list(background),
    }


def wcag_audit(app_name: Optional[str] = None,
               contrast_pairs: Optional[List[Dict[str, Any]]] = None,
               texts: Optional[List[str]] = None, level: str = "AA",
               min_target_px: int = 24,
               max_results: int = 500) -> Dict[str, Any]:
    from je_auto_control.utils.a11y_audit import wcag_audit as _wcag
    return _wcag(
        app_name=app_name, contrast_pairs=contrast_pairs, texts=texts,
        level=str(level), min_target_px=int(min_target_px),
        max_results=int(max_results))


# --- Mobile device matrix --------------------------------------------------

def run_device_matrix(actions: List[Any], devices: List[Dict[str, Any]],
                      max_parallel: int = 4,
                      var_name: str = "device") -> Dict[str, Any]:
    from je_auto_control.utils.device_matrix import run_on_devices
    return run_on_devices(
        actions, devices, max_parallel=int(max_parallel), var_name=var_name,
    ).to_dict()


# --- Media assertions ------------------------------------------------------

def assert_audio(duration_s: float = 1.0,
                 threshold: float = 0.01,
                 expect_sound: bool = True,
                 samplerate: int = 44100,
                 channels: int = 1,
                 raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.media_assert import assert_audio_activity
    return assert_audio_activity(
        duration_s=float(duration_s), threshold=float(threshold),
        expect_sound=bool(expect_sound), samplerate=int(samplerate),
        channels=int(channels), raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def assert_video_changes(video_path: str,
                         start_s: float = 0.0,
                         end_s: Optional[float] = None,
                         threshold: float = 1.0,
                         expect_motion: bool = True,
                         region: Optional[List[int]] = None,
                         raise_on_fail: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.media_assert import (
        assert_video_changes as _assert,
    )
    return _assert(
        video_path, start_s=float(start_s),
        end_s=None if end_s is None else float(end_s),
        threshold=float(threshold), expect_motion=bool(expect_motion),
        region=region, raise_on_fail=bool(raise_on_fail),
    ).to_dict()
