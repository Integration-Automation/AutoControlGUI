import sys
from typing import Tuple, Optional
from ctypes import windll
from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

from je_auto_control.windows.core.utils.win32_ctype_input import (
    Input, user32, Mouse, MouseInput, SendInput, wintypes, ctypes
)
from je_auto_control.windows.core.utils.win32_vk import (
    WIN32_LEFTDOWN, WIN32_LEFTUP,
    WIN32_MIDDLEDOWN, WIN32_MIDDLEUP,
    WIN32_RIGHTDOWN, WIN32_RIGHTUP,
    WIN32_XBUTTON1, WIN32_XBUTTON2,
    WIN32_DOWN, WIN32_XUP,
    WIN32_WHEEL, WIN32_WHEEL_DELTA
)
from je_auto_control.windows.screen.win32_screen import size

# 定義滑鼠按鍵事件 Define mouse button events
win32_mouse_left: Tuple[int, int, int] = (WIN32_LEFTUP, WIN32_LEFTDOWN, 0)
win32_mouse_middle: Tuple[int, int, int] = (WIN32_MIDDLEUP, WIN32_MIDDLEDOWN, 0)
win32_mouse_right: Tuple[int, int, int] = (WIN32_RIGHTUP, WIN32_RIGHTDOWN, 0)
win32_mouse_x1: Tuple[int, int, int] = (WIN32_XUP, WIN32_DOWN, WIN32_XBUTTON1)
win32_mouse_x2: Tuple[int, int, int] = (WIN32_XUP, WIN32_DOWN, WIN32_XBUTTON2)

# Window-message constants for the PostMessageW targeting path. The
# SendInput dwFlags above are *not* window messages, so posting a button
# tuple straight into PostMessageW's UINT ``Msg`` slot is a type error;
# these WM_*/MK_* values are what a window actually expects.
WM_LBUTTONDOWN: int = 0x0201
WM_LBUTTONUP: int = 0x0202
WM_RBUTTONDOWN: int = 0x0204
WM_RBUTTONUP: int = 0x0205
WM_MBUTTONDOWN: int = 0x0207
WM_MBUTTONUP: int = 0x0208
WM_XBUTTONDOWN: int = 0x020B
WM_XBUTTONUP: int = 0x020C
MK_LBUTTON: int = 0x0001
MK_RBUTTON: int = 0x0002
MK_MBUTTON: int = 0x0010
MK_XBUTTON1: int = 0x0020
MK_XBUTTON2: int = 0x0040
_XBUTTON1_HI: int = 0x0001
_XBUTTON2_HI: int = 0x0002

# Map a button tuple to (down_msg, down_wparam, up_msg, up_wparam). The X
# buttons pack the button id into the wParam high word, per WM_XBUTTON*.
_WINDOW_MESSAGE_TABLE: dict = {
    win32_mouse_left: (WM_LBUTTONDOWN, MK_LBUTTON, WM_LBUTTONUP, 0),
    win32_mouse_right: (WM_RBUTTONDOWN, MK_RBUTTON, WM_RBUTTONUP, 0),
    win32_mouse_middle: (WM_MBUTTONDOWN, MK_MBUTTON, WM_MBUTTONUP, 0),
    win32_mouse_x1: (
        WM_XBUTTONDOWN, (_XBUTTON1_HI << 16) | MK_XBUTTON1,
        WM_XBUTTONUP, _XBUTTON1_HI << 16,
    ),
    win32_mouse_x2: (
        WM_XBUTTONDOWN, (_XBUTTON2_HI << 16) | MK_XBUTTON2,
        WM_XBUTTONUP, _XBUTTON2_HI << 16,
    ),
}

_get_cursor_pos = windll.user32.GetCursorPos
_set_cursor_pos = windll.user32.SetCursorPos


def _convert_position(x: int, y: int) -> Tuple[int, int]:
    """
    將螢幕座標轉換成絕對座標
    Convert screen coordinates to absolute coordinates
    """
    width, height = size()
    converted_x = 65536 * x // width + 1
    converted_y = 65536 * y // height + 1
    return converted_x, converted_y


def mouse_event(event: int, x: int, y: int, dw_data: int = 0) -> None:
    """
    觸發滑鼠事件
    Trigger mouse event

    :param event: 滑鼠事件代碼 Mouse event code
    :param x: X 座標 X position
    :param y: Y 座標 Y position
    :param dw_data: 滾輪數值 Wheel data
    """
    converted_x, converted_y = _convert_position(x, y)
    ctypes.windll.user32.mouse_event(
        event,
        ctypes.c_long(converted_x),
        ctypes.c_long(converted_y),
        dw_data,
        0
    )


def position() -> Optional[Tuple[int, int]]:
    """
    取得滑鼠目前位置
    Get current mouse position
    """
    point = wintypes.POINT()
    if _get_cursor_pos(ctypes.byref(point)):
        return point.x, point.y
    return None


def set_position(x: int, y: int) -> None:
    """
    設定滑鼠位置
    Set mouse position
    """
    _set_cursor_pos(x, y)


def press_mouse(press_button: Tuple[int, int, int]) -> None:
    """
    模擬按下滑鼠按鍵
    Simulate mouse button press
    """
    SendInput(
        1,
        ctypes.byref(Input(type=Mouse, _input=Input.INPUTUnion(
            mi=MouseInput(dwFlags=press_button[1], mouseData=press_button[2])
        ))),
        ctypes.sizeof(Input)
    )


def release_mouse(release_button: Tuple[int, int, int]) -> None:
    """
    模擬放開滑鼠按鍵
    Simulate mouse button release
    """
    SendInput(
        1,
        ctypes.byref(Input(type=Mouse, _input=Input.INPUTUnion(
            mi=MouseInput(dwFlags=release_button[0], mouseData=release_button[2])
        ))),
        ctypes.sizeof(Input)
    )


def click_mouse(mouse_keycode: Tuple[int, int, int], x: Optional[int] = None, y: Optional[int] = None) -> None:
    """
    模擬滑鼠點擊
    Simulate mouse click

    :param mouse_keycode: 滑鼠按鍵代碼 Mouse keycode tuple
    :param x: X 座標 (可選) X position (optional)
    :param y: Y 座標 (可選) Y position (optional)
    """
    if x is not None and y is not None:
        set_position(x, y)
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value: int, x: int = 0, y: int = 0) -> None:
    """
    模擬滑鼠滾輪
    Simulate mouse scroll

    :param scroll_value: 滾動刻度數，正值向上、負值向下
        Scroll notches; positive scrolls up, negative down.
    :param x: X 座標 X position
    :param y: Y 座標 Y position
    """
    # dwData 以 WHEEL_DELTA (120) 為單位，必須換算，否則傳入 5 只會滾動
    # 5/120 個刻度，等同沒有作用。
    # dwData is measured in WHEEL_DELTA units, so a notch count must be scaled:
    # passing 5 raw moves 5/120 of a notch, i.e. nothing perceptible.
    mouse_event(WIN32_WHEEL, x, y, dw_data=int(scroll_value) * WIN32_WHEEL_DELTA)


def _resolve_window_messages(
        mouse_keycode: Tuple[int, int, int]) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Translate a button tuple into ``((down_msg, down_wparam), (up_msg, up_wparam))``.

    :param mouse_keycode: a button tuple from ``mouse_keys_table``
    :raises AutoControlException: when the button is not a known tuple
    """
    entry = _WINDOW_MESSAGE_TABLE.get(mouse_keycode) if isinstance(mouse_keycode, tuple) else None
    if entry is None:
        raise AutoControlException(f"Unsupported window mouse button: {mouse_keycode!r}")
    down_msg, down_wparam, up_msg, up_wparam = entry
    return (down_msg, down_wparam), (up_msg, up_wparam)


def send_mouse_event_to_window(window, mouse_keycode: Tuple[int, int, int],
                               x: int = 0, y: int = 0):
    """
    將滑鼠事件送到指定視窗
    Send mouse event to a specific window

    :param window: 視窗 HWND Window handle
    :param mouse_keycode: 滑鼠按鍵代碼 tuple Mouse button tuple
    :param x: X 座標 X position
    :param y: Y 座標 Y position
    """
    if window is None:
        raise AutoControlException("Invalid window handle")
    lparam = (int(y) << 16) | int(x)
    (down_msg, down_wparam), (up_msg, up_wparam) = _resolve_window_messages(mouse_keycode)
    user32.PostMessageW(window, down_msg, down_wparam, lparam)
    user32.PostMessageW(window, up_msg, up_wparam, lparam)