import sys
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import linux_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 Linux 環境執行，否則拋出例外
if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error_message)

from Xlib import X
from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display


def size() -> Tuple[int, int]:
    """
    Get screen size
    取得螢幕大小 (寬度, 高度)

    :return: (width, height) 螢幕寬度與高度
    """
    return display.screen().width_in_pixels, display.screen().height_in_pixels


def get_pixel_rgb(x: int, y: int) -> Tuple[int, int, int]:
    """
    Get RGB value of pixel at given coordinates
    取得指定座標的像素 RGB 值

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :return: (R, G, B) 三原色值
    """
    # 建立 root window 物件 Create root window object
    root = display.screen().root

    # 取得影像資料 Get image data
    raw = root.get_image(x, y, 1, 1, X.ZPixmap, 0xffffffff)

    # raw.data 是 bytes，需要轉換成 RGB
    pixel = tuple(raw.data[:3])  # (R, G, B)
    return pixel