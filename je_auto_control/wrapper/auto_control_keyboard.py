import sys

from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_hotkey
from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_press_key
from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_release_key
from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_type_key
from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_write
from je_auto_control.utils.je_auto_control_exception.exception_tag import keyboard_write_cant_find
from je_auto_control.utils.je_auto_control_exception.exception_tag import table_cant_find_key
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlCantFindKeyException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlKeyboardException
from je_auto_control.wrapper.platform_wrapper import keyboard
from je_auto_control.wrapper.platform_wrapper import keyboard_check
from je_auto_control.wrapper.platform_wrapper import keys_table


def press_key(keycode: int, is_shift: bool = False):
    """
    :param keycode which keycode we want to press
    :param is_shift shift is press?
    """
    if type(keycode) is not int:
        try:
            keycode = keys_table.get(keycode)
        except Exception:
            raise AutoControlCantFindKeyException(table_cant_find_key)
    try:
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            keyboard.press_key(keycode)
        elif sys.platform in ["darwin"]:
            keyboard.press_key(keycode, is_shift=is_shift)
    except Exception:
        raise AutoControlKeyboardException(keyboard_press_key)


def release_key(keycode: int, is_shift: bool = False):
    """
    :param keycode which keycode we want to release
    :param is_shift shift is press?
    """
    if type(keycode) is not int:
        try:
            keycode = keys_table.get(keycode)
        except Exception:
            raise AutoControlCantFindKeyException(table_cant_find_key)
    try:
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            keyboard.release_key(keycode)
        elif sys.platform in ["darwin"]:
            keyboard.release_key(keycode, is_shift=is_shift)
    except Exception:
        raise AutoControlKeyboardException(keyboard_release_key)


def type_key(keycode: int, is_shift: bool = False):
    """
    :param keycode which keycode we want to type
    :param is_shift shift is press?
    """
    try:
        press_key(keycode, is_shift)
        release_key(keycode, is_shift)
    except AutoControlKeyboardException:
        raise AutoControlKeyboardException(keyboard_type_key)


def check_key_is_press(keycode: int):
    """
    :param keycode check key press?
    """
    if type(keycode) is int:
        get_key_code = keycode
    else:
        get_key_code = keys_table.get(keycode)
    return keyboard_check.check_key_is_press(keycode=get_key_code)


def write(write_string: str, is_shift: bool = False):
    """
    :param write_string while string not on write_string+1 type_key(string)
    :param is_shift shift is press?
    """
    try:
        for single_string in write_string:
            try:
                if keys_table.get(single_string) is not None:
                    type_key(single_string, is_shift)
                else:
                    raise AutoControlKeyboardException
            except AutoControlKeyboardException:
                raise AutoControlKeyboardException(keyboard_write_cant_find)
    except AutoControlKeyboardException:
        raise AutoControlKeyboardException(keyboard_write)


def hotkey(key_code_list: list, is_shift: bool = False):
    """
    :param key_code_list press and release all key on list and reverse
    :param is_shift shift is press?
    """
    try:
        for key in key_code_list:
            press_key(key, is_shift)
        key_code_list.reverse()
        for key in key_code_list:
            release_key(key, is_shift)
    except AutoControlKeyboardException:
        raise AutoControlKeyboardException(keyboard_hotkey)
