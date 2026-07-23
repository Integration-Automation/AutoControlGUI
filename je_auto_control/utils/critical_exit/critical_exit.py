import _thread
from threading import Event, Thread
from typing import Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.auto_control_keyboard import _resolve_keycode
from je_auto_control.wrapper.platform_wrapper import keyboard_check

# 輪詢間隔，避免佔滿一顆 CPU 核心
# Poll interval; without it the listener busy-spins and pegs a CPU core.
_POLL_INTERVAL_SECONDS: float = 0.02


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
        :raises AutoControlCantFindKeyException: 平台鍵盤對應表缺少預設的 f7 鍵
        """
        super().__init__()
        self.daemon = default_daemon
        # 預設退出鍵為 F7 Default exit key is F7
        self._exit_check_key: int = _resolve_keycode("f7")
        self._stop_event = Event()

    def set_critical_key(self, keycode: Union[int, str] = None) -> None:
        """
        設定退出鍵
        Set critical exit key

        傳入 None 時維持原本的按鍵不變。
        Passing None leaves the current key unchanged.

        :param keycode: 可傳入 int (keycode) 或 str (鍵名)
        :raises AutoControlCantFindKeyException: 找不到對應的鍵名
        """
        if keycode is None:
            return
        # 解析失敗必須立刻拋出：靜默存入 None 會讓監聽執行緒在輪詢時死亡，
        # 使緊急退出鍵無聲失效。
        # Resolve eagerly: silently storing None would kill the listener
        # thread on its first poll, leaving the panic key dead with no signal.
        self._exit_check_key = _resolve_keycode(keycode)

    def stop(self) -> None:
        """
        停止監聽器
        Stop the listener loop
        """
        self._stop_event.set()

    def run(self) -> None:
        """
        執行監聽迴圈
        Run listener loop
        - 以固定間隔輪詢指定鍵盤按鍵
        - 按下時中斷主程式一次後結束監聽
        """
        try:
            # wait() 兼作節流與停止訊號：回傳 True 代表已呼叫 stop()。
            # wait() doubles as the throttle and the stop signal: it returns
            # True only once stop() has been called.
            while not self._stop_event.wait(_POLL_INTERVAL_SECONDS):
                if keyboard_check.check_key_is_press(self._exit_check_key):
                    # 只中斷一次。持續中斷會打斷主程式的 KeyboardInterrupt
                    # 處理與清理程式碼。
                    # Interrupt once. Firing every poll while the key is still
                    # held would interrupt the main thread's own
                    # KeyboardInterrupt handler and its cleanup code.
                    _thread.interrupt_main()
                    return
        # 守護執行緒無法將例外往外拋，靜默死亡會讓緊急退出鍵失效，
        # 因此刻意攔截所有例外並完整記錄。
        # A daemon listener cannot propagate anything to the caller; dying
        # silently is the exact failure this class must avoid, so catch
        # broadly and log loudly.
        except Exception as error:  # noqa: BLE001  # reason: see comment above
            autocontrol_logger.error(
                "critical exit listener failed: %r", error, exc_info=True)

    def init_critical_exit(self) -> None:
        """
        啟動緊急退出監聽器
        Initialize critical exit listener
        """
        self.start()