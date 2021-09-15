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

    def set_critical_key(self, keycode):
        """
        :param keycode which keycode we want to check is press ?
        """
        if type(keycode) is int:
            self._exit_check_key = keycode
        else:
            self._exit_check_key = keys_table.get(keycode)

    def run(self):
        """
        listener keycode _exit_check_key
        """
        try:
            while True:
                if keyboard_listener.check_key_is_press(self._exit_check_key):
                    _thread.interrupt_main()
        except AutoControlException:
            raise AutoControlException(je_auto_control_critical_exit_error)

    def init_critical_exit(self):
        """
        should only use this to start critical exit
        may this function will add more
        """
        critical_thread = self
        critical_thread.start()
