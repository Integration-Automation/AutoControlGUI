import sys

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

import Quartz


def check_key_is_press(keycode: int) -> bool:
    """
    Check if a specific key is currently pressed
    檢查指定的鍵是否正在被按下

    :param keycode: (int) The keycode to check 要檢查的鍵盤代碼
    :return: True if pressed, False otherwise 若按下則回傳 True，否則 False
    """
    # Quartz.CGEventSourceKeyState(source, keycode)
    # source = 0 表示使用預設事件來源
    return Quartz.CGEventSourceKeyState(0, keycode)