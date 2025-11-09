import sys
from typing import Any
from queue import Queue

from je_auto_control.utils.exception.exception_tags import linux_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 Linux 環境執行，否則拋出例外
if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error_message)

from je_auto_control.linux_with_x11.listener.x11_linux_listener import (
    x11_linux_record,
    x11_linux_stop_record,
)

# === 事件類型與細節對照表 Event type & detail mapping ===
type_dict = {
    5: "mouse",            # 事件類型 5 -> 滑鼠事件
    3: "AC_type_keyboard", # 事件類型 3 -> 鍵盤事件
}
detail_dict = {
    1: "AC_mouse_left",    # 滑鼠左鍵
    2: "AC_mouse_middle",  # 滑鼠中鍵
    3: "AC_mouse_right",   # 滑鼠右鍵
}


class X11LinuxRecorder:
    """
    X11 Linux Recorder
    X11 錄製控制器
    - 負責建立 Queue 並啟動事件錄製
    - 將原始事件轉換成可讀的動作序列
    """

    def __init__(self):
        self.record_queue: Queue | None = None
        self.result_queue: Queue | None = None

    def record(self) -> None:
        """
        Start recording events
        開始錄製事件，建立新的 Queue
        """
        self.record_queue = Queue()
        x11_linux_record(self.record_queue)

    def stop_record(self) -> Queue[Any]:
        """
        Stop recording and format results
        停止錄製，並將結果轉換成動作序列 Queue
        """
        self.result_queue = x11_linux_stop_record()
        action_queue = Queue()

        # 將原始事件轉換成可讀格式
        for details in list(self.result_queue.queue):
            if details[0] == 5:  # 滑鼠事件
                action_queue.put(
                    (detail_dict.get(details[1]), details[2], details[3])
                )
            elif details[0] == 3:  # 鍵盤事件
                action_queue.put(
                    (type_dict.get(details[0]), details[1])
                )

        return action_queue


# === 全域 Recorder 實例 Global Recorder Instance ===
x11_linux_recorder = X11LinuxRecorder()