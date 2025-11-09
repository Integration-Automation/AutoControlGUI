import _thread
import sys
from threading import Thread

from je_auto_control.wrapper.auto_control_keyboard import keyboard_keys_table
from je_auto_control.wrapper.platform_wrapper import keyboard_check


class CriticalExit(Thread):
    """
    CriticalExit
    緊急退出監聽器
    - 透過指定的鍵盤按鍵中斷主程式
    - 預設為 F7 鍵
    """

    def __init__(self, default_daemon: bool = True):
        """
        初始化 CriticalExit
        Initialize CriticalExit

        :param default_daemon: 是否設為守護執行緒 (程式結束時自動停止)
        """
        super().__init__()
        self.daemon = default_daemon
        # 預設退出鍵為 F7 Default exit key is F7
        self._exit_check_key: int = keyboard_keys_table.get("f7")

    def set_critical_key(self, keycode: int | str = None) -> None:
        """
        設定退出鍵
        Set critical exit key

        :param keycode: 可傳入 int (keycode) 或 str (鍵名)
        """
        if isinstance(keycode, int):
            self._exit_check_key = keycode
        elif isinstance(keycode, str):
            self._exit_check_key = keyboard_keys_table.get(keycode)

    def run(self) -> None:
        """
        執行監聽迴圈
        Run listener loop
        - 持續監聽指定鍵盤按鍵
        - 當按下時觸發中斷主程式
        """
        try:
            while True:
                if keyboard_check.check_key_is_press(self._exit_check_key):
                    _thread.interrupt_main()  # 中斷主程式 Interrupt main thread
        except Exception as error:
            print(repr(error), file=sys.stderr)

    def init_critical_exit(self) -> None:
        """
        啟動緊急退出監聽器
        Initialize critical exit listener
        """
        self.start()