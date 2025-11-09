import sys
from queue import Queue

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException, AutoControlJsonActionException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

from je_auto_control.osx.listener.osx_listener import osx_record, osx_stop_record


class OSXRecorder:
    """
    OSXRecorder
    macOS 事件錄製控制器
    - 提供開始與停止錄製的介面
    - 將錄製結果存入 Queue
    """

    def __init__(self):
        self.record_flag: bool = False

    def record(self) -> None:
        """
        Start recording events
        開始錄製事件
        """
        self.record_flag = True
        osx_record()

    def stop_record(self) -> Queue:
        """
        Stop recording and return recorded events
        停止錄製並回傳事件隊列

        :raises AutoControlJsonActionException: 若沒有錄製到任何事件
        :return: Queue of recorded events 錄製事件的隊列
        """
        record_queue = osx_stop_record()
        self.record_flag = False

        if record_queue is None:
            raise AutoControlJsonActionException

        return record_queue


# === 全域 Recorder 實例 Global Recorder Instance ===
osx_recorder = OSXRecorder()