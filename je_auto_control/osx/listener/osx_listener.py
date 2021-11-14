import sys

from je_auto_control.utils.je_auto_control_exception.exception_tag import osx_import_error
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException

if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error)


from Cocoa import *
import time
from Foundation import *
from PyObjCTools import AppHelper

from queue import Queue


record_queue = Queue()

app = NSApplication.sharedApplication()


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, aNotification):
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, keyboard_handler)
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskLeftMouseDown, mouse_left_handler)
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskRightMouseDown, mouse_right_handler)


def mouse_left_handler(event):
    loc = NSEvent.mouseLocation()
    record_queue.put(("mouse_left", loc.x, loc.y))


def mouse_right_handler(event):
    loc = NSEvent.mouseLocation()
    record_queue.put(("mouse_right", loc.x, loc.y))


def keyboard_handler(event):
    if int(event.keyCode()) == 98:
        pass
    else:
        record_queue.put(("type_key", int(hex(event.keyCode()), 16)))
        print(event)


def osx_record():
    record_queue = Queue()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


def osx_stop_record():
    return record_queue


if __name__ == "__main__":
    osx_record()

