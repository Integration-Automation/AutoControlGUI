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


def _decode_pixel(data: bytes) -> Tuple[int, int, int]:
    """Decode a little-endian TrueColor pixel buffer into ``(R, G, B)``.

    ``root.get_image`` returns the pixel in the server's native byte
    order; on the dominant little-endian TrueColor visual the bytes are
    laid out blue, green, red(, unused), so the first three must be
    reversed to yield true RGB — matching the windows / osx backends,
    which all return ``(R, G, B)``.

    :param data: raw ZPixmap bytes (at least three: B, G, R)
    :return: (R, G, B)
    """
    blue, green, red = data[0], data[1], data[2]
    return red, green, blue


def size() -> Tuple[int, int]:
    """
    Get screen size
    取得螢幕大小 (寬度, 高度)

    :return: (width, height) 螢幕寬度與高度
    """
    return display.screen().width_in_pixels, display.screen().height_in_pixels


def get_pixel(x: int, y: int) -> Tuple[int, int, int]:
    """
    Get RGB value of pixel at given coordinates
    取得指定座標的像素 RGB 值

    名稱需與 wrapper 呼叫的 ``screen.get_pixel`` 一致。
    Named to match the backend contract the wrapper calls
    (``screen.get_pixel``), as the windows / osx backends do.

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :return: (R, G, B) 三原色值
    """
    # 建立 root window 物件 Create root window object
    root = display.screen().root

    # 取得影像資料 Get image data
    raw = root.get_image(x, y, 1, 1, X.ZPixmap, 0xffffffff)

    # raw.data 是 little-endian BGR(X) 位元組，需轉成 RGB
    return _decode_pixel(raw.data)