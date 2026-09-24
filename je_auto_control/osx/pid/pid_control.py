import subprocess  # nosec B404  # reason: required to invoke osascript with argv list

from Quartz import CGEventCreateKeyboardEvent, CGEventPostToPid


def send_key_to_pid(pid: int, keycode: int) -> None:
    """
    Send a key press + release event to a specific process by PID
    將鍵盤事件 (按下 + 釋放) 傳送到指定的 PID

    Posted with ``CGEventPostToPid``. The Carbon ``CGEventPostToPSN`` path
    passed ``id(psn)`` -- the Python object's address, not the struct's --
    so the events went to a garbage process serial number.

    :param pid: Process ID 目標應用程式的 PID
    :param keycode: Keycode 要傳送的鍵盤代碼
    """
    for is_down in (True, False):
        CGEventPostToPid(int(pid), CGEventCreateKeyboardEvent(None, int(keycode), is_down))


def get_pid_by_window_title(title: str) -> int | None:
    """
    Get process PID by window title
    透過視窗標題取得應用程式的 PID

    :param title: Window title 視窗標題
    :return: PID (int) or None 若找到則回傳 PID，否則回傳 None
    """
    # 轉義 AppleScript 字串中的特殊字元 Escape special characters for AppleScript
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    # AppleScript 腳本，用來搜尋視窗標題
    script = f'''
    set targetWindowName to "{escaped_title}"
    tell application "System Events"
        repeat with proc in processes
            repeat with win in windows of proc
                if name of win contains targetWindowName then
                    return unix id of proc
                end if
            end repeat
        end repeat
    end tell
    '''
    try:
        pid_str = subprocess.check_output(  # nosec B603 B607  # reason: argv list, osascript on PATH; title is escaped
            ["osascript", "-e", script],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode().strip()
        return int(pid_str) if pid_str else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None