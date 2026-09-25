"""MCP adapters for windows, processes and the rest of the desktop session.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.

Covers window management, processes and the shell, opening files, idle and
sleep, volume, session lock, IME state, field verification and retries,
colour contrast, change ranking, widget classification and the clipboard.
"""
import base64
import os
from typing import Any, Dict, List, Optional

from je_auto_control.utils.mcp_server.tools._base import MCPContent


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


def foreground_window_pid() -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        foreground_window_process_id as _pid,
    )
    return {"pid": _pid() or 0}


def window_pid(title_substring: str,
               case_sensitive: bool = False) -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        window_process_id as _pid,
    )
    return {"pid": _pid(title_substring, case_sensitive=case_sensitive) or 0}


def windows_for_pid(pid: int, titled_only: bool = False) -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        windows_for_process_id as _windows,
    )
    return {"windows": [{"hwnd": hwnd, "title": title}
                        for hwnd, title in _windows(int(pid), titled_only)]}


def minimize_windows_for_pid(pid: int) -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        minimize_windows_for_process as _minimize,
    )
    return {"minimized": _minimize(int(pid))}


def post_key_to_window(title_substring: str, key: str,
                       case_sensitive: bool = False) -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        post_key_to_window as _post,
    )
    return {"posted": bool(_post(title_substring, key,
                                 case_sensitive=case_sensitive))}


def post_click_to_window(title_substring: str, button: str = "left",
                         x: int = 0, y: int = 0,
                         case_sensitive: bool = False) -> Dict[str, Any]:
    from je_auto_control.wrapper.auto_control_window import (
        post_click_to_window as _post,
    )
    return {"posted": bool(_post(title_substring, button, int(x), int(y),
                                 case_sensitive=case_sensitive))}


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
    # The process may exit between any two of these calls.
    try:
        proc.terminate()
        proc.wait(timeout=float(timeout))
        return "terminated"
    except psutil.NoSuchProcess:
        return "terminated"
    except psutil.TimeoutExpired:
        pass
    try:
        proc.kill()
    except psutil.NoSuchProcess:
        pass
    return "killed"


def shell_command(command: str, timeout: float = 30.0
                  ) -> Dict[str, Any]:
    """Run a shell-style command line and return stdout/stderr/exit_code.

    Never enables a shell: the line becomes an argv list (POSIX) or a
    ``CreateProcess`` command line (Windows) via ``command_args``, which
    protects against the command injection classes Bandit B602 / B605
    cover.
    """
    import locale

    from je_auto_control.utils.shell_process.shell_exec import command_args, run_captured
    if not command or not command.strip():
        raise ValueError("command must be a non-empty string")
    proc = run_captured(command_args(command), float(timeout))
    # Bytes, decoded leniently: strict decoding failed in the reader thread
    # on output the locale's code page cannot read, and stdout came back None.
    encoding = locale.getpreferredencoding(False)
    return {
        "exit_code": int(proc.returncode),
        "stdout": proc.stdout.decode(encoding, errors="replace"),
        "stderr": proc.stderr.decode(encoding, errors="replace"),
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
