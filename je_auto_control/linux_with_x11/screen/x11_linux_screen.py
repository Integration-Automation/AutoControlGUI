import sys
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import linux_import_error
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error)

from Xlib import X
from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display

def size() -> Tuple[int, int]:
    """
    get screen size
    """
    return display.screen().width_in_pixels, display.screen().height_in_pixels


def get_pixel_rgb(x: int, y: int) -> Tuple[int, int, int]:
    root = display.Display().screen().root
    root.get_image(x, y, 1, 1, X.ZPixmap, 0xffffffff)
    raw = root.get_image(x, y, 1, 1, X.ZPixmap, 0xffffffff)
    pixel = tuple(raw.data)[:3]  # (R, G, B)
    return pixel
