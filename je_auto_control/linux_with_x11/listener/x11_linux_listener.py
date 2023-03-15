import sys
from queue import Queue

from je_auto_control.utils.exception.exception_tags import linux_import_error
from je_auto_control.utils.exception.exception_tags import listener_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

from Xlib.display import Display
from Xlib import X
from Xlib.ext import record
from Xlib.protocol import rq

from threading import Thread

# get current display
current_display = Display()


class KeypressHandler(Thread):

    def __init__(self, default_daemon: bool = True):
        """
        setDaemon : default damon is true
        still listener : continue listener keycode ?
        event_key_code : now current key code default is 0
        """
        super().__init__()
        self.setDaemon(default_daemon)
        self.still_listener = True
        self.record_flag = False
        self.record_queue = None
        self.event_keycode = 0
        self.event_position = 0, 0

    # two times because press and release
    def check_is_press(self, keycode: int) -> bool:
        """
        :param keycode we want to check
        """
        if keycode == self.event_keycode:
            self.event_keycode = 0
            return True
        else:
            return False

    def run(self, reply) -> None:
        """
        :param reply listener return data
        get data
        while data not null and still listener
            get event

        """
        try:
            data = reply.data
            while len(data) and self.still_listener:
                event, data = rq.EventField(None).parse_binary_value(data, current_display.display, None, None)
                if event.detail != 0:
                    if event.type is X.ButtonRelease or event.type is X.KeyRelease:
                        self.event_keycode = event.detail
                        self.event_position = event.root_x, event.root_y
                        if self.record_flag is True:
                            temp = (event.type, event.detail, event.root_x, event.root_y)
                            self.record_queue.put(temp)
        except AutoControlException:
            raise AutoControlException(listener_error)

    def record(self, record_queue) -> None:
        """
        :param record_queue the queue test_record action
        """
        self.record_flag = True
        self.record_queue = record_queue

    def stop_record(self) -> Queue:
        self.record_flag = False
        return self.record_queue


class XWindowsKeypressListener(Thread):

    def __init__(self, default_daemon=True):
        """
        :param default_daemon default kill when program down
        create handler
        set root
        """
        super().__init__()
        self.setDaemon(default_daemon)
        self.still_listener = True
        self.handler = KeypressHandler()
        self.root = current_display.screen().root
        self.context = None

    def check_is_press(self, keycode: int):
        """
        :param keycode check this keycode is press?
        """
        return self.handler.check_is_press(keycode)

    def run(self) -> None:
        """
        while still listener
            get context
            set handler
            set test_record
            get event
        """
        if self.still_listener:
            try:
                # Monitor keypress and button press
                if self.context is None:
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
                        }])
                    current_display.record_enable_context(self.context, self.handler.run)
                    current_display.record_free_context(self.context)
                # keep running this to get event
                self.root.display.next_event()
            except AutoControlException:
                raise AutoControlException(listener_error)
            finally:
                self.handler.still_listener = False
                self.still_listener = False

    def record(self, record_queue) -> None:
        self.handler.record(record_queue)

    def stop_record(self) -> Queue:
        return self.handler.stop_record()


xwindows_listener = XWindowsKeypressListener()
xwindows_listener.start()


def check_key_is_press(keycode: int) -> int:
    """
    :param keycode check this keycode is press?
    """
    return xwindows_listener.check_is_press(keycode)


def x11_linux_record(record_queue) -> None:
    """
    :param record_queue the queue test_record action
    """
    xwindows_listener.record(record_queue)


def x11_linux_stop_record() -> Queue:
    """
    stop test_record action
    """
    return xwindows_listener.stop_record()
