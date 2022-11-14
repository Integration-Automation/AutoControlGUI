import _thread
import sys
from threading import Thread

from je_auto_control.wrapper.auto_control_keyboard import keys_table
from je_auto_control.wrapper.platform_wrapper import keyboard_check


class CriticalExit(Thread):
    """
    use to make program interrupt
    """

    def __init__(self, default_daemon: bool = True):
        """
        default interrupt is keyboard F7 key
        :param default_daemon bool thread setDaemon
        """
        super().__init__()
        self.setDaemon(default_daemon)
        self._exit_check_key: int = keys_table.get("f7")

    def set_critical_key(self, keycode: [int, str] = None) -> None:
        """
        set interrupt key
        :param keycode interrupt key
        """
        if isinstance(keycode, int):
            self._exit_check_key = keycode
        else:
            self._exit_check_key = keys_table.get(keycode)

    def run(self) -> None:
        """
        listener keycode _exit_check_key to interrupt
        """
        try:
            while True:
                if keyboard_check.check_key_is_press(self._exit_check_key):
                    _thread.interrupt_main()
        except Exception as error:
            print(repr(error), file=sys.stderr)

    def init_critical_exit(self) -> None:
        """
        should only use this to start critical exit
        may this function will add more
        """
        critical_thread = self
        critical_thread.start()
