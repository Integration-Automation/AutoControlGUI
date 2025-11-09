import objc
import subprocess
from ctypes import cdll, c_void_p

from Quartz import CGEventCreateKeyboardEvent
from ApplicationServices import ProcessSerialNumber, GetProcessForPID

# 載入 Carbon 函式庫 Load Carbon framework
carbon = cdll.LoadLibrary('/System/Library/Frameworks/Carbon.framework/Carbon')


def send_key_to_pid(pid: int, keycode: int) -> None:
    """
    Send a key press + release event to a specific process by PID
    將鍵盤事件 (按下 + 釋放) 傳送到指定的 PID

    :param pid: Process ID 目標應用程式的 PID
    :param keycode: Keycode 要傳送的鍵盤代碼
    """
    psn = ProcessSerialNumber()
    GetProcessForPID(pid, objc.byref(psn))

    # 建立按下事件 Create key down event
    event_down = CGEventCreateKeyboardEvent(None, keycode, True)
    # 建立釋放事件 Create key up event
    event_up = CGEventCreateKeyboardEvent(None, keycode, False)

    # 傳送事件到指定的 ProcessSerialNumber
    carbon.CGEventPostToPSN(c_void_p(id(psn)), event_down)
    carbon.CGEventPostToPSN(c_void_p(id(psn)), event_up)


def get_pid_by_window_title(title: str) -> int | None:
    """
    Get process PID by window title
    透過視窗標題取得應用程式的 PID

    :param title: Window title 視窗標題
    :return: PID (int) or None 若找到則回傳 PID，否則回傳 None
    """
    # AppleScript 腳本，用來搜尋視窗標題
    script = f'''
    set targetWindowName to "{title}"
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
        pid_str = subprocess.check_output(
            ["osascript", "-e", script],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return int(pid_str) if pid_str else None
    except subprocess.CalledProcessError:
        return None