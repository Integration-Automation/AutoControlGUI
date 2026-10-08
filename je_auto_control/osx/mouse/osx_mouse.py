import sys
import time
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlMouseException,
)

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

    NSEvent.mouseLocation() 的原點在左下角，但本模組送出的 CGEvent 事件
    以左上角為原點，因此必須翻轉 y。未翻轉時，未指定座標的點擊會落在
    垂直鏡像的位置（只有游標剛好在畫面正中央時才正確）。
    NSEvent.mouseLocation() has a bottom-left origin, while the CGEvents this
    module posts use a top-left origin — as do the windows and x11 backends.
    Without flipping y, a coordinate read here and fed back into press/click
    (which is exactly what mouse_preprocess does when x/y are omitted) lands
    at the vertically mirrored point.

    :return: (x, y) 滑鼠座標，原點為左上角 top-left origin
    """
    loc = Quartz.NSEvent.mouseLocation()
    # 用點(point)為單位的顯示高度翻轉 y。CGDisplayPixelsHigh 回傳的是像素
    # 高度,在 Retina/HiDPI 螢幕上是點高度的 2 倍,會讓翻轉後的 y 落在錯誤位置。
    # mouseLocation() 與這裡送出的 CGEvent 都以點為單位。
    # Flip y using the point-based display height. CGDisplayPixelsHigh returns
    # pixels (2x the point height on Retina/HiDPI), which would offset the
    # flipped y; mouseLocation() and the posted CGEvents are both in points.
    height = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height
    return int(loc.x), int(height - loc.y)


def mouse_event(event: int, x: int, y: int, mouse_button: int,
                click_count: int = 1) -> None:
    """
    Create and post a mouse event
    建立並送出滑鼠事件

    :param event: Quartz event type 事件類型 (例如 kCGEventMouseMoved)
    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    :param click_count: 這是連續第幾次點擊 Which click of a run this is (>= 1)
    """
    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap,
        _build_mouse_event(event, x, y, mouse_button, click_count))


def _build_mouse_event(event: int, x: int, y: int, mouse_button: int,
                       click_count: int = 1):
    """
    The Quartz event ``mouse_event`` posts, not yet posted
    建立（但不送出）滑鼠事件

    macOS 的應用程式不從兩次點擊的時間差判定雙擊，而是讀事件上的點擊次數欄位
    （``kCGMouseEventClickState``）。這裡原本從不寫它，所以連點兩次只是兩次
    單擊；``click_count`` 大於 1 時寫進去，等於 1 時事件與以前完全相同。
    A macOS application does not infer a double-click from the timing of two
    clicks: it reads the click-state field of the event. This never wrote it,
    so two clicks were two single clicks. A ``click_count`` above 1 is written
    into the field; at 1 the event is exactly the one this always built.
    """
    count = _click_count(click_count)
    curr_event = Quartz.CGEventCreateMouseEvent(None, event, (x, y), mouse_button)
    if count != 1:
        Quartz.CGEventSetIntegerValueField(
            curr_event, Quartz.kCGMouseEventClickState, count)
    return curr_event


def _click_count(click_count: int) -> int:
    """``click_count`` as an int >= 1, else raise ``AutoControlMouseException``."""
    if isinstance(click_count, bool) or not isinstance(click_count, int) or click_count < 1:
        raise AutoControlMouseException(
            f"click_count must be an integer >= 1, got {click_count!r}")
    return click_count


def double_click_interval() -> float:
    """
    The longest gap, in seconds, the system still counts as one multi-click
    系統仍視為連擊的最長間隔（秒）

    使用者可在系統設定調整；兩次點擊隔得比這更久，就是兩次獨立的單擊。
    User-adjustable in System Settings; two clicks further apart than this
    are two separate single clicks.
    """
    return float(Quartz.NSEvent.doubleClickInterval())


def set_position(x: int, y: int) -> None:
    """
    Move mouse to specific position
    移動滑鼠到指定座標

    :param x: target x position 目標 X 座標
    :param y: target y position 目標 Y 座標
    """
    mouse_event(Quartz.kCGEventMouseMoved, x, y, 0)


def press_mouse(x: int, y: int, mouse_button: int, click_count: int = 1) -> None:
    """
    Press mouse button
    模擬按下滑鼠按鍵

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    :param click_count: 這是連續第幾次點擊 Which click of a run this is (>= 1)
    """
    if mouse_button == osx_mouse_left:
        mouse_event(Quartz.kCGEventLeftMouseDown, x, y, Quartz.kCGMouseButtonLeft, click_count)
    elif mouse_button == osx_mouse_middle:
        mouse_event(Quartz.kCGEventOtherMouseDown, x, y, Quartz.kCGMouseButtonCenter, click_count)
    elif mouse_button == osx_mouse_right:
        mouse_event(Quartz.kCGEventRightMouseDown, x, y, Quartz.kCGMouseButtonRight, click_count)
    else:   # nothing was posted, and the wrapper reported the press done
        raise AutoControlMouseException(f"unknown mouse button {mouse_button!r}")


def release_mouse(x: int, y: int, mouse_button: int, click_count: int = 1) -> None:
    """
    Release mouse button
    模擬釋放滑鼠按鍵

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    :param click_count: 這是連續第幾次點擊，與對應的按下相同
        Which click of a run this is; the same number as the matching press
    """
    if mouse_button == osx_mouse_left:
        mouse_event(Quartz.kCGEventLeftMouseUp, x, y, Quartz.kCGMouseButtonLeft, click_count)
    elif mouse_button == osx_mouse_middle:
        mouse_event(Quartz.kCGEventOtherMouseUp, x, y, Quartz.kCGMouseButtonCenter, click_count)
    elif mouse_button == osx_mouse_right:
        mouse_event(Quartz.kCGEventRightMouseUp, x, y, Quartz.kCGMouseButtonRight, click_count)
    else:
        raise AutoControlMouseException(f"unknown mouse button {mouse_button!r}")


def click_mouse(x: int, y: int, mouse_button: int, click_count: int = 1) -> None:
    """
    Perform mouse click (press + release)
    模擬滑鼠點擊（按下 + 釋放）

    :param x: X coordinate X 座標
    :param y: Y coordinate Y 座標
    :param mouse_button: Mouse button code 滑鼠按鍵代碼
    :param click_count: 這是連續第幾次點擊；雙擊的第二下傳 2
        Which click of a run this is; the second click of a double-click is 2
    """
    press_mouse(x, y, mouse_button, click_count)
    time.sleep(0.001)  # 小延遲確保事件正確送出
    release_mouse(x, y, mouse_button, click_count)


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