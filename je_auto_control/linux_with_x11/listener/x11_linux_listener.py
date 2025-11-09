import sys
from queue import Queue
from threading import Thread

from je_auto_control.utils.exception.exception_tags import linux_import_error_message, listener_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 Linux 環境執行，否則拋出例外
if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error_message)

from Xlib.display import Display
from Xlib import X
from Xlib.ext import record
from Xlib.protocol import rq

# 取得目前的 X11 Display
current_display = Display()


class KeypressHandler(Thread):
    """
    KeypressHandler
    鍵盤事件處理器
    - 負責解析 X11 事件
    - 可選擇記錄事件到 Queue
    """

    def __init__(self, default_daemon: bool = True):
        """
        :param default_daemon: 是否設為守護執行緒 (程式結束時自動停止)
        """
        super().__init__()
        self.daemon = default_daemon
        self.still_listener = True
        self.record_flag = False
        self.record_queue = None
        self.event_keycode = 0
        self.event_position = (0, 0)

    def check_is_press(self, keycode: int) -> bool:
        """
        檢查指定 keycode 是否被按下
        Check if the given keycode was pressed
        """
        if keycode == self.event_keycode:
            self.event_keycode = 0
            return True
        return False

    def run(self, reply) -> None:
        """
        處理 X11 回傳的事件資料
        Handle X11 reply data and parse events
        """
        try:
            data = reply.data
            while len(data) and self.still_listener:
                event, data = rq.EventField(None).parse_binary_value(
                    data, current_display.display, None, None
                )
                if event.detail != 0:
                    if event.type in (X.ButtonRelease, X.KeyRelease):
                        self.event_keycode = event.detail
                        self.event_position = (event.root_x, event.root_y)

                        # 如果開啟記錄模式，將事件放入 Queue
                        if self.record_flag and self.record_queue is not None:
                            temp = (event.type, event.detail, event.root_x, event.root_y)
                            self.record_queue.put(temp)
        except Exception:
            raise AutoControlException(listener_error_message)

    def record(self, record_queue: Queue) -> None:
        """
        開始記錄事件
        Start recording events into the given queue
        """
        self.record_flag = True
        self.record_queue = record_queue

    def stop_record(self) -> Queue:
        """
        停止記錄事件並回傳 Queue
        Stop recording and return the recorded queue
        """
        self.record_flag = False
        return self.record_queue


class XWindowsKeypressListener(Thread):
    """
    XWindowsKeypressListener
    X11 鍵盤/滑鼠事件監聽器
    - 建立 Record Context
    - 啟動 KeypressHandler
    """

    def __init__(self, default_daemon=True):
        super().__init__()
        self.daemon = default_daemon
        self.still_listener = True
        self.handler = KeypressHandler()
        self.root = current_display.screen().root
        self.context = None

    def check_is_press(self, keycode: int) -> bool:
        """
        檢查指定 keycode 是否被按下
        Check if the given keycode was pressed
        """
        return self.handler.check_is_press(keycode)

    def run(self) -> None:
        """
        啟動監聽迴圈
        Start listening loop for X11 events
        """
        if self.still_listener:
            try:
                if self.context is None:
                    # 建立 Record Context
                    self.context = current_display.record_create_context(
                        0,
                        [record.AllClients],
                        [{
                            'core_requests': (0, 0),
                            'core_replies': (0, 0),
                            'ext_requests': (0, 0, 0, 0),
                            'ext_replies': (0, 0, 0, 0),
                            'delivered_events': (0, 0),
                            'device_events': (X.KeyReleaseMask, X.ButtonReleaseMask),
                            'errors': (0, 0),
                            'client_started': False,
                            'client_died': False,
                        }]
                    )
                    # 啟用事件監聽
                    current_display.record_enable_context(self.context, self.handler.run)
                    current_display.record_free_context(self.context)

                # 持續等待事件
                self.root.display.next_event()
            except Exception:
                raise AutoControlException(listener_error_message)
            finally:
                self.handler.still_listener = False
                self.still_listener = False

    def record(self, record_queue: Queue) -> None:
        """
        開始記錄事件
        Start recording events
        """
        self.handler.record(record_queue)

    def stop_record(self) -> Queue:
        """
        停止記錄事件
        Stop recording events
        """
        return self.handler.stop_record()


# === 全域監聽器 Global Listener ===
xwindows_listener = XWindowsKeypressListener()
xwindows_listener.start()


def check_key_is_press(keycode: int) -> bool:
    """
    檢查指定 keycode 是否被按下
    Check if the given keycode was pressed
    """
    return xwindows_listener.check_is_press(keycode)


def x11_linux_record(record_queue: Queue) -> None:
    """
    開始記錄事件
    Start recording events into the given queue
    """
    xwindows_listener.record(record_queue)


def x11_linux_stop_record() -> Queue:
    """
    停止記錄事件並回傳 Queue
    Stop recording and return the recorded queue
    """
    return xwindows_listener.stop_record()