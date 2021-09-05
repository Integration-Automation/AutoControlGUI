import _thread
import sys
from threading import Thread

from je_auto_control.utils.je_auto_control_exception.exception_tag import je_auto_control_critical_exit_error
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlException
from je_auto_control.wrapper.auto_control_keyboard import keys_table
from je_auto_control.wrapper.platform_wrapper import keyboard_listener


class CriticalExit(Thread):

    def __init__(self, default_daemon=True):
        super().__init__()
        self.setDaemon(default_daemon)
        self._exit_check_key = keys_table.get("f7")

    def set_critical_key(self, key):
        if type(key) is int:
            self._exit_check_key = key
        else:
            self._exit_check_key = keys_table.get(key)

    def run(self):
        try:
            while True:
                if keyboard_listener.check_key_is_press(self._exit_check_key):
                    _thread.interrupt_main()
        except AutoControlException:
            raise AutoControlException(je_auto_control_critical_exit_error)

    def init_critical_exit(self):
        critical_thread = self
        critical_thread.start()
