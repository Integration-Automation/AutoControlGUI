import sys

if sys.platform not in ["darwin"]:
    raise Exception("should be only loaded on MacOS")


from Cocoa import *
import time
from Foundation import *
from PyObjCTools import AppHelper

from queue import Queue


class RecordQueue(object):

    def __init__(self):
        self.record_queue = None

    def reset_queue(self):
        self.record_queue = Queue()


record_queue_manager = RecordQueue()

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, aNotification):
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, keyboard_handler)
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskLeftMouseDown, mouse_left_handler)
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskRightMouseDown, mouse_right_handler)


def mouse_left_handler(event):
    loc = NSEvent.mouseLocation()
    record_queue_manager.record_queue.put(("mouse_left", loc.x, loc.y))


def mouse_right_handler(event):
    loc = NSEvent.mouseLocation()
    record_queue_manager.record_queue.put(("mouse_right", loc.x, loc.y))


def keyboard_handler(event):
    record_queue_manager.record_queue.put(("keyboard", int(hex(event.keyCode()), 16)))
    if int(event.keyCode()) == 98:
        AppHelper.stopEventLoop()


def osx_record():
    record_queue_manager.reset_queue()
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    NSApp().setDelegate_(delegate)
    AppHelper.runEventLoop()


def osx_stop_record():
    return record_queue_manager.record_queue


if __name__ == "__main__":
    osx_record()

