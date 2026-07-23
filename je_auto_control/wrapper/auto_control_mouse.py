import ctypes
import sys
from typing import Tuple, Union

from je_auto_control.utils.exception.exception_tags import (
    mouse_click_mouse_error_message, mouse_get_position_error_message, mouse_press_mouse_error_message,
    mouse_release_mouse_error_message, mouse_scroll_error_message, mouse_set_position_error_message,
    mouse_wrong_value_error_message, table_cant_find_key_error_message
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlCantFindKeyException, AutoControlMouseException
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.auto_control_screen import screen_size
from je_auto_control.wrapper.platform_wrapper import mouse, mouse_keys_table, special_mouse_keys_table


def get_mouse_table() -> dict:
    """
    取得滑鼠按鍵對應表
    Get mouse keys table
    """
    return mouse_keys_table


def mouse_preprocess(mouse_keycode: Union[int, str], x: int, y: int) -> Tuple[int, int, int]:
    """
    前置處理：檢查 keycode 並補齊座標
    Preprocess mouse keycode and coordinates

    :param mouse_keycode: 滑鼠按鍵代碼或字串 Mouse keycode or string
    :param x: X 座標
    :param y: Y 座標
    :return: (keycode, x, y)
    """
    try:
        if isinstance(mouse_keycode, str):
            mouse_keycode = mouse_keys_table.get(mouse_keycode)
            if mouse_keycode is None:
                raise AutoControlCantFindKeyException(table_cant_find_key_error_message)
    except AutoControlCantFindKeyException as error:
        raise AutoControlCantFindKeyException(table_cant_find_key_error_message) from error

    # 只有在座標缺漏時才查詢游標位置。
    # Only query the cursor when a coordinate is actually missing: backends
    # that cannot report the cursor (Wayland raises NotImplementedError by
    # design) must still accept an explicit x/y, which is what lets scripts
    # replay the same effect headlessly.
    if x is None or y is None:
        try:
            now_x, now_y = get_mouse_position()
            if x is None:
                x = now_x
            if y is None:
                y = now_y
        except AutoControlMouseException as error:
            raise AutoControlMouseException(
                mouse_get_position_error_message + " " + repr(error)) from error

    # Coerce coordinates to int before they reach a native input call. A float
    # x/y (from a computed/random variable or a JSON literal like {"x": 100.5})
    # would hit an un-prototyped SetCursorPos / Xlib fake_input and raise
    # ctypes.ArgumentError / struct.error — which escapes the executor and
    # aborts the whole run instead of clicking at the rounded point.
    if x is not None:
        x = int(x)
    if y is not None:
        y = int(y)
    return mouse_keycode, x, y


def get_mouse_position() -> tuple[int, int] | None:
    """
    取得滑鼠目前位置
    Get current mouse position

    :return: (x, y)
    """
    autocontrol_logger.info("get_mouse_position")
    try:
        record_action_to_list("get_mouse_position", None)
        return mouse.position()
    except AutoControlMouseException as error:
        raise AutoControlMouseException(mouse_get_position_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("get_mouse_position", None, repr(error))
        autocontrol_logger.error(f"get_mouse_position failed: {repr(error)}")
        raise


def set_mouse_position(x: int, y: int) -> tuple[int, int] | None:
    """
    設定滑鼠位置
    Set mouse position

    :param x: X 座標
    :param y: Y 座標
    :return: (x, y)
    """
    autocontrol_logger.info(f"set_mouse_position, x={x}, y={y}")
    param = {"x": x, "y": y}
    try:
        # int coercion: a float coord would reach an un-prototyped native call
        # (SetCursorPos / Xlib fake_input) and raise ctypes.ArgumentError /
        # struct.error, which escapes the executor and aborts the whole run.
        x, y = int(x), int(y)
        mouse.set_position(x=x, y=y)
        record_action_to_list("set_mouse_position", param)
        return x, y
    except AutoControlMouseException as error:
        autocontrol_logger.error(f"set_mouse_position failed: {repr(error)}")
        raise AutoControlMouseException(mouse_set_position_error_message + " " + repr(error)) from error
    except ctypes.ArgumentError as error:
        autocontrol_logger.error(f"set_mouse_position invalid args: {repr(error)}")
        raise AutoControlMouseException(mouse_wrong_value_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("set_mouse_position", param, repr(error))
        autocontrol_logger.error(f"set_mouse_position failed: {repr(error)}")
        raise


def press_mouse(mouse_keycode: Union[int, str], x: int = None, y: int = None) -> tuple[int, int, int] | None:
    """
    按下滑鼠按鍵
    Press mouse button

    :return: (keycode, x, y)
    """
    autocontrol_logger.info(f"press_mouse, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"keycode": mouse_keycode, "x": x, "y": y}
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            mouse.press_mouse(mouse_keycode)
        elif sys.platform == "darwin":
            mouse.press_mouse(x, y, mouse_keycode)
        record_action_to_list("press_mouse", param)
        return mouse_keycode, x, y
    except AutoControlMouseException as error:
        autocontrol_logger.error(f"press_mouse failed: {repr(error)}")
        raise AutoControlMouseException(mouse_press_mouse_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("press_mouse", param, repr(error))
        autocontrol_logger.error(f"press_mouse failed: {repr(error)}")
        raise


def release_mouse(mouse_keycode: Union[int, str], x: int = None, y: int = None) -> tuple[int, int, int] | None:
    """
    放開滑鼠按鍵
    Release mouse button

    :return: (keycode, x, y)
    """
    autocontrol_logger.info(f"release_mouse, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"keycode": mouse_keycode, "x": x, "y": y}
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            mouse.release_mouse(mouse_keycode)
        elif sys.platform == "darwin":
            mouse.release_mouse(x, y, mouse_keycode)
        record_action_to_list("release_mouse", param)
        return mouse_keycode, x, y
    except AutoControlMouseException as error:
        autocontrol_logger.error(f"release_mouse failed: {repr(error)}")
        raise AutoControlMouseException(mouse_release_mouse_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("release_mouse", param, repr(error))
        autocontrol_logger.error(f"release_mouse failed: {repr(error)}")
        raise


def click_mouse(mouse_keycode: Union[int, str], x: int = None, y: int = None) -> Tuple[int, int, int]:
    """
    在指定座標按下並放開滑鼠按鍵
    Click mouse button at given position

    :param mouse_keycode: 滑鼠按鍵代碼 Mouse keycode
    :param x: X 座標 X position
    :param y: Y 座標 Y position
    :return: (keycode, x, y)
    """
    autocontrol_logger.info(f"click_mouse, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"keycode": mouse_keycode, "x": x, "y": y}
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        # macOS orders its mouse backend as (x, y, button) — same convention as
        # press_mouse/release_mouse above. Without this branch the arguments
        # bind as x=<keycode>, y=<x>, button=<y>; the osx button table holds
        # strings, so the int never matches any branch and the click is
        # silently dropped with no exception.
        if sys.platform == "darwin":
            mouse.click_mouse(x, y, mouse_keycode)
        else:
            mouse.click_mouse(mouse_keycode, x, y)
        record_action_to_list("click_mouse", param)
        return mouse_keycode, x, y
    except AutoControlMouseException as error:
        record_action_to_list("click_mouse", param, repr(error))
        autocontrol_logger.error(f"click_mouse failed: {repr(error)}")
        raise AutoControlMouseException(mouse_click_mouse_error_message + " " + repr(error)) from error


def _scroll_to(x: int, y: int) -> None:
    """
    將游標移到滾動位置，缺漏的座標沿用目前位置並做邊界檢查。
    Move the cursor to the requested scroll point, filling in whichever
    coordinate was omitted from the current position and clamping to screen.

    只有在有座標缺漏時才查詢游標位置：兩個座標都給定時，不需要（也不應該）
    查詢游標，否則無法回報游標的後端（如 Wayland）會誤拋例外。
    Query the cursor only when a coordinate is missing: when both are
    supplied the current position is never needed, so backends that cannot
    report it (e.g. Wayland) must not be forced to raise.
    """
    width, height = screen_size()
    if x is None or y is None:
        try:
            now_x, now_y = get_mouse_position()
        except (AutoControlMouseException, NotImplementedError, OSError):
            # 後端無法回報游標(如 Wayland 會拋 NotImplementedError)時,無法
            # 補上缺漏的座標軸,直接略過預先移動,讓滾動發生在目前游標處,
            # 而非讓例外逸出 API 承諾的降級行為。
            # Backend can't report the cursor (Wayland raises NotImplementedError);
            # without it the omitted axis can't be filled, so skip the pre-move and
            # scroll at the current cursor instead of escaping the documented
            # graceful degradation.
            return
    else:
        now_x, now_y = (None, None)
    target_x = now_x if x is None else max(0, min(x, width - 1))
    target_y = now_y if y is None else max(0, min(y, height - 1))
    set_mouse_position(target_x, target_y)


def mouse_scroll(scroll_value: int, x: int = None, y: int = None,
                 scroll_direction: str = "scroll_down") -> Tuple[int, str]:
    """
    模擬滑鼠滾輪操作
    Simulate mouse scroll

    :param scroll_value: 滾動數值 Scroll value
    :param x: X 座標，指定時會先將游標移到該處 X position; the cursor moves here first
    :param y: Y 座標，指定時會先將游標移到該處 Y position; the cursor moves here first
    :param scroll_direction: 滾動方向 (Linux only) Scroll direction
    :return: (scroll_value, scroll_direction)
    """
    autocontrol_logger.info(f"mouse_scroll, value={scroll_value}, x={x}, y={y}, direction={scroll_direction}")
    param = {"scroll_value": scroll_value, "x": x, "y": y, "direction": scroll_direction}
    try:
        # 只有在呼叫端指定座標時才移動游標。
        # Only move when the caller asked for a point. Every backend ignored
        # the x/y it was handed (Win32 needs MOVE|ABSOLUTE alongside WHEEL,
        # and the mac/linux backends were never passed them), so scrolling
        # always happened at the cursor despite the documented API. Querying
        # the cursor unconditionally also broke backends that cannot report
        # it, e.g. Wayland.
        if x is not None or y is not None:
            _scroll_to(x, y)

        if sys.platform in ["win32", "cygwin", "msys"]:
            mouse.scroll(scroll_value)
        elif sys.platform == "darwin":
            mouse.scroll(scroll_value)
        elif sys.platform in ["linux", "linux2"]:
            scroll_direction = special_mouse_keys_table.get(scroll_direction, scroll_direction)
            mouse.scroll(scroll_value, scroll_direction)

        record_action_to_list("mouse_scroll", param)
        return scroll_value, scroll_direction

    except AutoControlMouseException as error:
        autocontrol_logger.error(f"mouse_scroll failed: {repr(error)}")
        raise AutoControlMouseException(mouse_scroll_error_message + " " + repr(error)) from error


def send_mouse_event_to_window(window, mouse_keycode: Union[int, str],
                               x: int = None, y: int = None) -> None:
    """
    將滑鼠事件送到指定視窗
    Send mouse event to a specific window

    :param window: 視窗 handle Window handle
    :param mouse_keycode: 滑鼠按鍵代碼 Mouse keycode
    :param x: X 座標 X position
    :param y: Y 座標 Y position
    """
    autocontrol_logger.info(f"send_mouse_event_to_window, window={window}, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"window": window, "keycode": mouse_keycode, "x": x, "y": y}
    try:
        if sys.platform == "darwin":
            autocontrol_logger.warning("send_mouse_event_to_window not supported on macOS")
            return

        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        mouse.send_mouse_event_to_window(window, mouse_keycode=mouse_keycode, x=x, y=y)
        record_action_to_list("send_mouse_event_to_window", param)

    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("send_mouse_event_to_window", param, repr(error))
        autocontrol_logger.error(f"send_mouse_event_to_window failed: {repr(error)}")
