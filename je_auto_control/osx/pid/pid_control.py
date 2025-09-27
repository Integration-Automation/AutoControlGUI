import objc
from Quartz import CGEventCreateKeyboardEvent, kCGEventKeyDown, kCGEventKeyUp
from ApplicationServices import ProcessSerialNumber, GetProcessForPID
from ctypes import cdll, c_void_p
import subprocess

carbon = cdll.LoadLibrary('/System/Library/Frameworks/Carbon.framework/Carbon')


def send_key_to_pid(pid, keycode):
    psn = ProcessSerialNumber()
    GetProcessForPID(pid, objc.byref(psn))
    event_down = CGEventCreateKeyboardEvent(None, keycode, True)
    event_up = CGEventCreateKeyboardEvent(None, keycode, False)
    carbon.CGEventPostToPSN(c_void_p(id(psn)), event_down)
    carbon.CGEventPostToPSN(c_void_p(id(psn)), event_up)

def get_pid_by_window_title(title: str):
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
