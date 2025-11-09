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
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
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
    except AutoControlCantFindKeyException:
        raise AutoControlCantFindKeyException(table_cant_find_key_error_message)

    try:
        now_x, now_y = get_mouse_position()
        if x is None:
            x = now_x
        if y is None:
            y = now_y
    except AutoControlMouseException as error:
        raise AutoControlMouseException(mouse_get_position_error_message + " " + repr(error))

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
        raise AutoControlMouseException(mouse_get_position_error_message + " " + repr(error))
    except Exception as error:
        record_action_to_list("get_mouse_position", None, repr(error))
        print(repr(error), file=sys.stderr)


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
        mouse.set_position(x=x, y=y)
        record_action_to_list("set_mouse_position", param)
        return x, y
    except AutoControlMouseException as error:
        autocontrol_logger.error(f"set_mouse_position failed: {repr(error)}")
        raise AutoControlMouseException(mouse_set_position_error_message + " " + repr(error))
    except ctypes.ArgumentError as error:
        autocontrol_logger.error(f"set_mouse_position invalid args: {repr(error)}")
        raise AutoControlMouseException(mouse_wrong_value_error_message + " " + repr(error))
    except Exception as error:
        record_action_to_list("set_mouse_position", param, repr(error))
        autocontrol_logger.error(f"set_mouse_position failed: {repr(error)}")


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
        raise AutoControlMouseException(mouse_press_mouse_error_message + " " + repr(error))
    except Exception as error:
        record_action_to_list("press_mouse", param, repr(error))
        autocontrol_logger.error(f"press_mouse failed: {repr(error)}")


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
        raise AutoControlMouseException(mouse_release_mouse_error_message + " " + repr(error))
    except Exception as error:
        record_action_to_list("release_mouse", param, repr(error))
        autocontrol_logger.error(f"release_mouse failed: {repr(error)}")


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
        mouse.click_mouse(mouse_keycode, x, y)
        record_action_to_list("click_mouse", param)
        return mouse_keycode, x, y
    except AutoControlMouseException as error:
        record_action_to_list("click_mouse", param, repr(error))
        autocontrol_logger.error(f"click_mouse failed: {repr(error)}")
        raise AutoControlMouseException(mouse_click_mouse_error_message + " " + repr(error))


def mouse_scroll(scroll_value: int, x: int = None, y: int = None,
                 scroll_direction: str = "scroll_down") -> Tuple[int, str]:
    """
    模擬滑鼠滾輪操作
    Simulate mouse scroll

    :param scroll_value: 滾動數值 Scroll value
    :param x: X 座標 X position
    :param y: Y 座標 Y position
    :param scroll_direction: 滾動方向 (Linux only) Scroll direction
    :return: (scroll_value, scroll_direction)
    """
    autocontrol_logger.info(f"mouse_scroll, value={scroll_value}, x={x}, y={y}, direction={scroll_direction}")
    param = {"scroll_value": scroll_value, "x": x, "y": y, "direction": scroll_direction}
    try:
        now_x, now_y = get_mouse_position()
        width, height = screen_size()

        # 邊界檢查 Boundary check
        x = now_x if x is None else max(0, min(x, width - 1))
        y = now_y if y is None else max(0, min(y, height - 1))

        if sys.platform in ["win32", "cygwin", "msys"]:
            mouse.scroll(scroll_value, x, y)
        elif sys.platform == "darwin":
            mouse.scroll(scroll_value)
        elif sys.platform in ["linux", "linux2"]:
            scroll_direction = special_mouse_keys_table.get(scroll_direction, scroll_direction)
            mouse.scroll(scroll_value, scroll_direction)

        record_action_to_list("mouse_scroll", param)
        return scroll_value, scroll_direction

    except AutoControlMouseException as error:
        autocontrol_logger.error(f"mouse_scroll failed: {repr(error)}")
        raise AutoControlMouseException(mouse_scroll_error_message + " " + repr(error))


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

    except Exception as error:
        record_action_to_list("send_mouse_event_to_window", param, repr(error))
        autocontrol_logger.error(f"send_mouse_event_to_window failed: {repr(error)}")
