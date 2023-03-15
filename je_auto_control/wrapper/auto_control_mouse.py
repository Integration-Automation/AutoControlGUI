import ctypes
import sys
from typing import Tuple, Union

from je_auto_control.utils.exception.exception_tags import mouse_click_mouse
from je_auto_control.utils.exception.exception_tags import mouse_get_position
from je_auto_control.utils.exception.exception_tags import mouse_press_mouse
from je_auto_control.utils.exception.exception_tags import mouse_release_mouse
from je_auto_control.utils.exception.exception_tags import mouse_scroll
from je_auto_control.utils.exception.exception_tags import mouse_set_position
from je_auto_control.utils.exception.exception_tags import mouse_wrong_value
from je_auto_control.utils.exception.exception_tags import table_cant_find_key
from je_auto_control.utils.exception.exceptions import AutoControlCantFindKeyException
from je_auto_control.utils.exception.exceptions import AutoControlMouseException
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.auto_control_screen import size
from je_auto_control.wrapper.platform_wrapper import mouse
from je_auto_control.wrapper.platform_wrapper import mouse_table
from je_auto_control.wrapper.platform_wrapper import special_table


def get_mouse_table():
    return mouse_table


def mouse_preprocess(mouse_keycode: [int, str], x: int, y: int) -> Tuple[Union[int, str], int, int]:
    """
    check mouse keycode is verified or not
    and then check current mouse position
    if x or y is None set x, y is current position
    :param mouse_keycode which mouse keycode we want to click
    :param x mouse click x position
    :param y mouse click y position
    """
    try:
        if isinstance(mouse_keycode, str):
            mouse_keycode = mouse_table.get(mouse_keycode)
        else:
            pass
    except AutoControlCantFindKeyException:
        raise AutoControlCantFindKeyException(table_cant_find_key)
    try:
        now_x, now_y = position()
        if x is None:
            x = now_x
        if y is None:
            y = now_y
    except AutoControlMouseException as error:
        raise AutoControlMouseException(mouse_get_position + " " + repr(error))
    return mouse_keycode, x, y


def position() -> Tuple[int, int]:
    """
    get mouse current position
    return mouse_x, mouse_y
    """
    try:
        try:
            record_action_to_list("position", None)
            return mouse.position()
        except AutoControlMouseException as error:
            raise AutoControlMouseException(mouse_get_position + " " + repr(error))
    except Exception as error:
        record_action_to_list("position", None, repr(error))
        print(repr(error), file=sys.stderr)


def set_position(x: int, y: int) -> Tuple[int, int]:
    """
    :param x set mouse position x
    :param y set mouse position y
    return x, y
    """
    param = locals()
    try:
        try:
            mouse.set_position(x=x, y=y)
            record_action_to_list("position", param)
            return x, y
        except AutoControlMouseException as error:
            raise AutoControlMouseException(mouse_set_position + " " + repr(error))
        except ctypes.ArgumentError as error:
            raise AutoControlMouseException(mouse_wrong_value + " " + repr(error))
    except Exception as error:
        record_action_to_list("set_position", param, repr(error))
        print(repr(error), file=sys.stderr)


def press_mouse(mouse_keycode: [int, str], x: int = None, y: int = None) -> Tuple[Union[int, str], int, int]:
    """
    press mouse keycode on x, y
    return keycode, x, y
    :param mouse_keycode which mouse keycode we want to press
    :param x mouse click x position
    :param y mouse click y position
    """
    param = locals()
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        try:
            if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
                mouse.press_mouse(mouse_keycode)
            elif sys.platform in ["darwin"]:
                mouse.press_mouse(x, y, mouse_keycode)
            record_action_to_list("press_mouse", param)
            return mouse_keycode, x, y
        except AutoControlMouseException as error:
            raise AutoControlMouseException(mouse_press_mouse + " " + repr(error))
        except TypeError as error:
            raise AutoControlMouseException(repr(error))
    except Exception as error:
        record_action_to_list("press_mouse", param, repr(error))
        print(repr(error), file=sys.stderr)


def release_mouse(mouse_keycode: [int, str], x: int = None, y: int = None) -> Tuple[Union[int, str], int, int]:
    """
    release mouse keycode on x, y
    return keycode, x, y
    :param mouse_keycode which mouse keycode we want to release
    :param x mouse click x position
    :param y mouse click y position
    """
    param = locals()
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        try:
            if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
                mouse.release_mouse(mouse_keycode)
            elif sys.platform in ["darwin"]:
                mouse.release_mouse(x, y, mouse_keycode)
            record_action_to_list("press_mouse", param)
            return mouse_keycode, x, y
        except AutoControlMouseException as error:
            raise AutoControlMouseException(mouse_release_mouse + " " + repr(error))
        except TypeError as error:
            raise AutoControlMouseException(repr(error))
    except Exception as error:
        record_action_to_list("release_mouse", param, repr(error))
        print(repr(error), file=sys.stderr)


def click_mouse(mouse_keycode: [int, str], x: int = None, y: int = None) -> Tuple[Union[int, str], int, int]:
    """
    press and release mouse keycode on x, y
    return keycode, x, y
    :param mouse_keycode which mouse keycode we want to click
    :param x mouse click x position
    :param y mouse click y position
    """
    param = locals()
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        try:
            mouse.click_mouse(mouse_keycode, x, y)
            record_action_to_list("click_mouse", param)
            return mouse_keycode, x, y
        except AutoControlMouseException as error:
            record_action_to_list("click_mouse", param, mouse_click_mouse + " " + repr(error))
            raise AutoControlMouseException(mouse_click_mouse + " " + repr(error))
        except TypeError as error:
            record_action_to_list("click_mouse", param, repr(error))
            raise AutoControlMouseException(repr(error))
    except Exception as error:
        record_action_to_list("click_mouse", param, repr(error))
        print(repr(error), file=sys.stderr)


def scroll(scroll_value: int, x: int = None, y: int = None, scroll_direction: str = "scroll_down") -> Tuple[int, str]:
    """"
    :param scroll_value scroll count
    :param x mouse click x position
    :param y mouse click y position
    :param scroll_direction which direction we want
    scroll_direction = scroll_up : direction up
    scroll_direction = scroll_down : direction down
    scroll_direction = scroll_left : direction left
    scroll_direction = scroll_right : direction right
    """
    param = locals()
    try:
        try:
            now_cursor_x, now_cursor_y = position()
        except AutoControlMouseException as error:
            record_action_to_list("scroll", param, repr(error))
            raise AutoControlMouseException(mouse_get_position)
        width, height = size()
        if x is None:
            x = now_cursor_x
        else:
            if x < 0:
                x = 0
            elif x >= width:
                x = width - 1
        if y is None:
            y = now_cursor_y
        else:
            if y < 0:
                y = 0
            elif y >= height:
                y = height - 1
        try:
            if sys.platform in ["win32", "cygwin", "msys"]:
                mouse.scroll(scroll_value, x, y)
            elif sys.platform in ["darwin"]:
                mouse.scroll(scroll_value)
            elif sys.platform in ["linux", "linux2"]:
                scroll_direction = special_table.get(scroll_direction)
                mouse.scroll(scroll_value, scroll_direction)
            return scroll_value, scroll_direction
        except AutoControlMouseException as error:
            raise AutoControlMouseException(mouse_scroll + " " + repr(error))
        except TypeError as error:
            raise AutoControlMouseException(repr(error))
    except Exception as error:
        record_action_to_list("scroll", param, repr(error))
        print(repr(error), file=sys.stderr)
