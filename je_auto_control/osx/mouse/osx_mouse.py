import sys
import time
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

import Quartz

from je_auto_control.osx.core.utils.osx_vk import (
    osx_mouse_left,
    osx_mouse_middle,
    osx_mouse_right,
)


def position() -> Tuple[int, int]:
    """
    Get current mouse position
    取得目前滑鼠座標位置

    :return: (x, y) 滑鼠座標
    """
    loc = Quartz.NSEvent.mouseLocation()
    return int(loc.x), int(loc.y)


def mouse_event(event: int, x: int, y: int, mouse_button: int) -> None:
    """
    Create and post a mouse event
    建立並送出滑鼠事件

    :param event: Quartz event type 事件類型 (例如 kCGEventMouseMoved)
    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    """
    curr_event = Quartz.CGEventCreateMouseEvent(None, event, (x, y), mouse_button)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, curr_event)


def set_position(x: int, y: int) -> None:
    """
    Move mouse to specific position
    移動滑鼠到指定座標

    :param x: target x position 目標 X 座標
    :param y: target y position 目標 Y 座標
    """
    mouse_event(Quartz.kCGEventMouseMoved, x, y, 0)


def press_mouse(x: int, y: int, mouse_button: int) -> None:
    """
    Press mouse button
    模擬按下滑鼠按鍵

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    """
    if mouse_button == osx_mouse_left:
        mouse_event(Quartz.kCGEventLeftMouseDown, x, y, Quartz.kCGMouseButtonLeft)
    elif mouse_button == osx_mouse_middle:
        mouse_event(Quartz.kCGEventOtherMouseDown, x, y, Quartz.kCGMouseButtonCenter)
    elif mouse_button == osx_mouse_right:
        mouse_event(Quartz.kCGEventRightMouseDown, x, y, Quartz.kCGMouseButtonRight)


def release_mouse(x: int, y: int, mouse_button: int) -> None:
    """
    Release mouse button
    模擬釋放滑鼠按鍵

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    """
    if mouse_button == osx_mouse_left:
        mouse_event(Quartz.kCGEventLeftMouseUp, x, y, Quartz.kCGMouseButtonLeft)
    elif mouse_button == osx_mouse_middle:
        mouse_event(Quartz.kCGEventOtherMouseUp, x, y, Quartz.kCGMouseButtonCenter)
    elif mouse_button == osx_mouse_right:
        mouse_event(Quartz.kCGEventRightMouseUp, x, y, Quartz.kCGMouseButtonRight)


def click_mouse(x: int, y: int, mouse_button: int) -> None:
    """
    Perform mouse click (press + release)
    模擬滑鼠點擊（按下 + 釋放）

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    """
    press_mouse(x, y, mouse_button)
    time.sleep(0.001)  # 小延遲確保事件正確送出
    release_mouse(x, y, mouse_button)


def scroll(scroll_value: int) -> None:
    """
    Perform mouse scroll
    模擬滑鼠滾動

    :param scroll_value: scroll count 滾動次數 (正數=向上, 負數=向下)
    """
    scroll_value = int(scroll_value)
    for _ in range(abs(scroll_value)):
        scroll_event = Quartz.CGEventCreateScrollWheelEvent(
            None,
            Quartz.kCGScrollEventUnitLine,  # 單位：行
            1,  # 軸數 (1 = 垂直)
            1 if scroll_value >= 0 else -1  # 滾動方向
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll_event)