import sys
from typing import Optional
from queue import Queue

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

from je_auto_control.windows.listener.win32_keyboard_listener import Win32KeyboardListener
from je_auto_control.windows.listener.win32_mouse_listener import Win32MouseListener


class Win32Recorder:
    """
    Win32Recorder
    Windows 錄製器
    - 可同時錄製滑鼠與鍵盤事件
    - 可選擇只錄製滑鼠或鍵盤
    """

    def __init__(self):
        self.mouse_record_listener: Optional[Win32MouseListener] = None
        self.keyboard_record_listener: Optional[Win32KeyboardListener] = None
        self.record_queue: Optional[Queue] = None
        self.result_queue: Optional[Queue] = None

    def record(self) -> None:
        """
        開始錄製滑鼠與鍵盤事件
        Start recording both mouse and keyboard events
        """
        self.mouse_record_listener = Win32MouseListener()
        self.keyboard_record_listener = Win32KeyboardListener()
        self.record_queue = Queue()
        self.mouse_record_listener.record(self.record_queue)
        self.keyboard_record_listener.record(self.record_queue)

    def stop_record(self) -> Queue:
        """
        停止錄製並回傳事件
        Stop recording and return recorded events
        """
        mouse_queue = self.mouse_record_listener.stop_record() if self.mouse_record_listener else Queue()
        keyboard_queue = self.keyboard_record_listener.stop_record() if self.keyboard_record_listener else Queue()

        # 合併兩個 Queue 的內容 Merge both queues
        self.result_queue = Queue()
        while not mouse_queue.empty():
            self.result_queue.put(mouse_queue.get())
        while not keyboard_queue.empty():
            self.result_queue.put(keyboard_queue.get())

        self.record_queue = None
        return self.result_queue

    def record_mouse(self) -> None:
        """
        開始錄製滑鼠事件
        Start recording mouse events
        """
        self.mouse_record_listener = Win32MouseListener()
        self.record_queue = Queue()
        self.mouse_record_listener.record(self.record_queue)

    def stop_record_mouse(self) -> Queue:
        """
        停止錄製滑鼠事件並回傳結果
        Stop recording mouse events and return results
        """
        self.result_queue = self.mouse_record_listener.stop_record() if self.mouse_record_listener else Queue()
        self.record_queue = None
        return self.result_queue

    def record_keyboard(self) -> None:
        """
        開始錄製鍵盤事件
        Start recording keyboard events
        """
        self.keyboard_record_listener = Win32KeyboardListener()
        self.record_queue = Queue()
        self.keyboard_record_listener.record(self.record_queue)

    def stop_record_keyboard(self) -> Queue:
        """
        停止錄製鍵盤事件並回傳結果
        Stop recording keyboard events and return results
        """
        self.result_queue = self.keyboard_record_listener.stop_record() if self.keyboard_record_listener else Queue()
        self.record_queue = None
        return self.result_queue


# 全域錄製器實例 Global recorder instance
win32_recorder = Win32Recorder()