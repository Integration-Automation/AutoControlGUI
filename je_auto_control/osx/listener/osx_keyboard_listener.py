from Cocoa import *
import time
from Foundation import *
from PyObjCTools import AppHelper

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, aNotification):
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSKeyDownMask, handler)

def handler(event):
    print(event)
    print(str(hex(event.keyCode())))

app = NSApplication.sharedApplication()
delegate = AppDelegate.alloc().init()
NSApp().setDelegate_(delegate)
AppHelper.runEventLoop()