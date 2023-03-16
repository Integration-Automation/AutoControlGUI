import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error)

from je_auto_control.windows.listener.win32_keyboard_listener import Win32KeyboardListener
from je_auto_control.windows.listener.win32_mouse_listener import Win32MouseListener

from queue import Queue


class Win32Recorder(object):

    def __init__(self):
        self.mouse_record_listener: [None, Win32MouseListener] = None
        self.keyboard_record_listener: [None, Win32KeyboardListener] = None
        self.record_queue: [None, Queue] = None
        self.result_queue: [None, Queue] = None

    def record(self) -> None:
        self.mouse_record_listener = Win32MouseListener()
        self.keyboard_record_listener = Win32KeyboardListener()
        self.record_queue = Queue()
        self.mouse_record_listener.record(self.record_queue)
        self.keyboard_record_listener.record(self.record_queue)

    def stop_record(self) -> Queue:
        self.result_queue = self.mouse_record_listener.stop_record()
        self.result_queue = self.keyboard_record_listener.stop_record()
        self.record_queue = None
        return self.result_queue

    def record_mouse(self) -> None:
        self.mouse_record_listener = Win32MouseListener()
        self.record_queue = Queue()
        self.mouse_record_listener.record(self.record_queue)

    def stop_record_mouse(self) -> Queue:
        self.result_queue = self.mouse_record_listener.stop_record()
        self.record_queue = None
        return self.result_queue

    def record_keyboard(self) -> None:
        self.keyboard_record_listener = Win32KeyboardListener()
        self.record_queue = Queue()
        self.keyboard_record_listener.record(self.record_queue)

    def stop_record_keyboard(self) -> Queue:
        self.result_queue = self.keyboard_record_listener.stop_record()
        self.record_queue = None
        return self.result_queue


win32_recorder = Win32Recorder()
