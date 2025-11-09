import sys
from queue import Queue

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

from Cocoa import *
from Foundation import *
from PyObjCTools import AppHelper

# === 全域事件記錄 Queue Global event record queue ===
record_queue = Queue()

# 建立 NSApplication 實例 Create NSApplication instance
app = NSApplication.sharedApplication()


class AppDelegate(NSObject):
    """
    AppDelegate
    應用程式委派類別
    - 負責在應用程式啟動後註冊全域事件監聽器
    """

    def applicationDidFinishLaunching_(self, aNotification):
        """
        註冊全域事件監聽器
        Register global event monitors
        """
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, keyboard_handler
        )
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskLeftMouseDown, mouse_left_handler
        )
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskRightMouseDown, mouse_right_handler
        )


def mouse_left_handler(event) -> None:
    """
    滑鼠左鍵事件處理器
    Mouse left button handler
    """
    loc = NSEvent.mouseLocation()
    record_queue.put(("AC_mouse_left", loc.x, loc.y))


def mouse_right_handler(event) -> None:
    """
    滑鼠右鍵事件處理器
    Mouse right button handler
    """
    loc = NSEvent.mouseLocation()
    record_queue.put(("AC_mouse_right", loc.x, loc.y))


def keyboard_handler(event) -> None:
    """
    鍵盤事件處理器
    Keyboard event handler
    """
    keycode = int(event.keyCode())
    if keycode == 98:  # 特殊情況：忽略 keycode 98
        return
    record_queue.put(("AC_type_keyboard", keycode))
    print(event)


def osx_record() -> None:
    """
    開始錄製事件
    Start recording events
    """
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


def osx_stop_record() -> Queue:
    """
    停止錄製並回傳事件 Queue
    Stop recording and return event queue
    """
    return record_queue