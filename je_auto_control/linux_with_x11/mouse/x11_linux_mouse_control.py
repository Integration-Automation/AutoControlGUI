import sys
import time
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import linux_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 Linux 環境執行，否則拋出例外
if sys.platform not in ["linux", "linux2"]:
    raise AutoControlException(linux_import_error_message)

from Xlib import X, protocol
from Xlib.ext.xtest import fake_input
from je_auto_control.linux_with_x11.core.utils.x11_linux_display import display

# === 滑鼠按鍵與滾動方向定義 Mouse button & scroll direction constants ===
x11_linux_mouse_left = 1
x11_linux_mouse_middle = 2
x11_linux_mouse_right = 3
x11_linux_scroll_direction_up = 4
x11_linux_scroll_direction_down = 5
x11_linux_scroll_direction_left = 6
x11_linux_scroll_direction_right = 7


def position() -> Tuple[int, int]:
    """
    Get current mouse position
    取得目前滑鼠座標位置
    """
    coord = display.screen().root.query_pointer()._data
    return coord["root_x"], coord["root_y"]


def set_position(x: int, y: int) -> None:
    """
    Move mouse to specific position
    移動滑鼠到指定座標

    :param x: target x position 目標 X 座標
    :param y: target y position 目標 Y 座標
    """
    time.sleep(0.01)
    fake_input(display, X.MotionNotify, x=x, y=y)
    display.sync()


def press_mouse(mouse_keycode: int) -> None:
    """
    Press mouse button
    模擬按下滑鼠按鍵

    :param mouse_keycode: mouse button code 滑鼠按鍵代碼
    """
    time.sleep(0.01)
    fake_input(display, X.ButtonPress, mouse_keycode)
    display.sync()


def release_mouse(mouse_keycode: int) -> None:
    """
    Release mouse button
    模擬釋放滑鼠按鍵

    :param mouse_keycode: mouse button code 滑鼠按鍵代碼
    """
    time.sleep(0.01)
    fake_input(display, X.ButtonRelease, mouse_keycode)
    display.sync()


def click_mouse(mouse_keycode: int, x: int = None, y: int = None) -> None:
    """
    Perform mouse click (press + release)
    模擬滑鼠點擊（按下 + 釋放）

    :param mouse_keycode: mouse button code 滑鼠按鍵代碼
    :param x: optional x position 選擇性 X 座標
    :param y: optional y position 選擇性 Y 座標
    """
    if x is not None and y is not None:
        set_position(x, y)
    press_mouse(mouse_keycode)
    release_mouse(mouse_keycode)


def scroll(scroll_value: int, scroll_direction: int) -> None:
    """
    Perform mouse scroll
    模擬滑鼠滾動

    :param scroll_value: number of scroll units 滾動次數
    :param scroll_direction: scroll direction 滾動方向
        4 = up 上
        5 = down 下
        6 = left 左
        7 = right 右
    """
    for _ in range(scroll_value):
        click_mouse(scroll_direction)


def send_mouse_event_to_window(window_id: int, mouse_keycode: int,
                               x: int = None, y: int = None) -> None:
    """
    Send mouse event directly to a specific window
    將滑鼠事件直接送到指定視窗

    :param window_id: target window ID 目標視窗 ID
    :param mouse_keycode: mouse button code 滑鼠按鍵代碼
    :param x: optional x position 選擇性 X 座標
    :param y: optional y position 選擇性 Y 座標
    """
    window = display.create_resource_object("window", window_id)
    for ev_type in (X.ButtonPress, X.ButtonRelease):
        ev = protocol.event.ButtonPress(
            time=X.CurrentTime,
            root=display.screen().root,
            window=window,
            same_screen=1,
            child=X.NONE,
            root_x=x, root_y=y, event_x=x, event_y=y,
            state=0,
            detail=mouse_keycode
        )
        ev.type = ev_type
        window.send_event(ev, propagate=True)
    display.flush()