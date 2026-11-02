"""Acquire and own an independent X11 RECORD connection on first observation."""
from queue import Queue
from threading import Event, Lock, Thread
from typing import Any, Optional

from je_auto_control.utils.exception.exception_tags import linux_import_error_message, listener_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.platform_id import is_x11_unix
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# === 平台檢查 Platform Check ===
# 僅允許在 Linux 環境執行，否則拋出例外
# Not "is this Linux" but "is this an X11 unix": a FreeBSD, OpenBSD or
# NetBSD desktop runs the same X server and the same python-Xlib, and
# nothing below is Linux-specific.
if not is_x11_unix():
    raise AutoControlException(linux_import_error_message)

from Xlib.display import Display
from Xlib import X
from Xlib.ext import record
from Xlib.protocol import rq



class KeypressHandler:
    """
    KeypressHandler
    鍵盤事件處理器
    - 負責解析 X11 事件
    - 可選擇記錄事件到 Queue

    Plain handler (not a Thread): instances are passed as the
    ``record_enable_context`` callback, never started as their own thread.
    """

    def __init__(self, default_daemon: bool = True, display: Any = None):
        """
        :param default_daemon: kept for backwards compatibility; the handler
            is no longer a Thread, so this flag is informational only.
        """
        self.display = display
        self.daemon = default_daemon
        self.still_listener = True
        self.record_flag = False
        self.record_queue: Optional[Queue] = None
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

    def handle_reply(self, reply) -> None:
        """
        處理 X11 回傳的事件資料
        Handle X11 reply data and parse events
        """
        try:
            data = reply.data
            while len(data) and self.still_listener:
                event, data = rq.EventField(None).parse_binary_value(
                    data, self.display.display, None, None
                )
                if event.detail != 0:
                    if event.type in (X.ButtonRelease, X.KeyRelease):
                        self.event_keycode = event.detail
                        self.event_position = (event.root_x, event.root_y)

                        # 如果開啟記錄模式，將事件放入 Queue
                        if self.record_flag and self.record_queue is not None:
                            temp = (event.type, event.detail, event.root_x, event.root_y)
                            self.record_queue.put(temp)
        except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
            raise AutoControlException(f"{listener_error_message}: {error}") from error

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

        沒有呼叫過 ``record()`` 就停止時回傳空 Queue：原本回的是 ``None``，
        而簽章承諾的是 Queue，於是 ``x11_linux_record`` 在讀它的 ``.queue``
        時拋 AttributeError。
        Returns an empty queue when ``record()`` was never called: it used to
        hand back the ``None`` it was constructed with, and the caller one
        frame up reads ``.queue`` off it.
        """
        self.record_flag = False
        if self.record_queue is None:
            return Queue()
        return self.record_queue


class XWindowsKeypressListener(Thread):
    """
    XWindowsKeypressListener
    X11 鍵盤/滑鼠事件監聽器
    - 建立 Record Context
    - 啟動 KeypressHandler
    """

    def __init__(self, default_daemon: bool = True):
        super().__init__(daemon=default_daemon)
        self.still_listener = True
        self._record_lock = Lock()
        self.context: Any = None
        self.handler = KeypressHandler()
        self.display: Any = None
        self.closed = Event()
        self.failure: Exception | None = None

    def prepare(self) -> None:
        """Acquire the dedicated connection and RECORD context synchronously."""
        self.display = Display()
        self.handler = KeypressHandler(display=self.display)
        self.context = self.display.record_create_context(
            0, [record.AllClients], [{
                'core_requests': (0, 0),
                'core_replies': (0, 0),
                'ext_requests': (0, 0, 0, 0),
                'ext_replies': (0, 0, 0, 0),
                'delivered_events': (0, 0),
                'device_events': (X.KeyReleaseMask, X.ButtonReleaseMask),
                'errors': (0, 0),
                'client_started': False,
                'client_died': False,
            }])

    def check_is_press(self, keycode: int) -> bool:
        """Consume the last observed matching key release."""
        return self.handler.check_is_press(keycode)

    def close(self) -> None:
        """Release owned resources; only successful close permits replacement."""
        with self._record_lock:
            self.still_listener = False
        try:
            try:
                if self.display is not None and self.context is not None:
                    self.display.record_free_context(self.context)
            finally:
                if self.display is not None:
                    self.display.close()
                self.display = None
                self.context = None
                self.closed.set()
        except Exception as error:
            self.failure = error
            raise AutoControlException(f"X11 listener cleanup failed: {error}") from error

    def close_after_failure(self, error: Exception) -> None:
        """Close owned resources while retaining the original failure evidence."""
        try:
            self.close()
        except AutoControlException as cleanup_error:
            autocontrol_logger.error("X11 listener cleanup after %r failed: %r", error, cleanup_error)

    def run(self) -> None:
        """Block in RECORD on this listener's independent connection."""
        try:
            self.display.record_enable_context(self.context, self.handler.handle_reply)
        except Exception as error:
            self.close_after_failure(error)
            raise AutoControlException(f"{listener_error_message}: {error}") from error
        else:
            self.close()
        finally:
            self.handler.still_listener = False

    def record(self, record_queue: Queue) -> None:
        """
        開始記錄事件
        Start recording events
        """
        with self._record_lock:
            if not self.still_listener:
                raise AutoControlException("X11 listener is retiring; recording was not started")
            self.handler.record(record_queue)

    def stop_record(self) -> Queue:
        """
        停止記錄事件
        Stop recording events
        """
        return self.handler.stop_record()


_LISTENER: XWindowsKeypressListener | None = None
_listener_lock = Lock()


def _get_listener(record_queue: Queue | None = None) -> XWindowsKeypressListener:
    global _LISTENER  # pylint: disable=global-statement  # reason: one module owns this lazy cache
    with _listener_lock:
        if _LISTENER is not None and not _LISTENER.closed.is_set() and _LISTENER.failure is not None:
            raise AutoControlException("Previous X11 listener cleanup is incomplete") from _LISTENER.failure
        if _LISTENER is None or _LISTENER.closed.is_set():
            candidate = XWindowsKeypressListener()
            try:
                candidate.prepare()
                if record_queue is not None:
                    candidate.record(record_queue)
                candidate.start()
            except Exception as error:
                candidate.close_after_failure(error)
                if not candidate.closed.is_set():
                    _LISTENER = candidate
                raise AutoControlException(f"{listener_error_message}: {error}") from error
            _LISTENER = candidate
        elif record_queue is not None:
            _LISTENER.record(record_queue)
        return _LISTENER


def check_key_is_press(keycode: int) -> bool:
    """Start observation on first use and consume a matching observed key."""
    return _get_listener().check_is_press(keycode)


def x11_linux_record(record_queue: Queue) -> None:
    """Arm the queue before starting a newly acquired RECORD listener."""
    _get_listener(record_queue)


def x11_linux_stop_record() -> Queue:
    """Stop queue insertion; stopping before first use acquires no resources."""
    with _listener_lock:
        return Queue() if _LISTENER is None else _LISTENER.stop_record()
