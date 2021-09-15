import sys

from je_auto_control.utils.je_auto_control_exception import exception_tag
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlCantFindKeyException
from je_auto_control.utils.je_auto_control_exception.exceptions import AutoControlKeyboardException
from je_auto_control.wrapper.platform_wrapper import keyboard
from je_auto_control.wrapper.platform_wrapper import keyboard_listener
from je_auto_control.wrapper.platform_wrapper import keys_table


def press_key(keycode, is_shift=False):
    try:
        keycode = keys_table.get(keycode)
    except Exception:
        raise AutoControlCantFindKeyException(exception_tag.table_cant_find_key)
    try:
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            keyboard.press_key(keycode)
        elif sys.platform in ["darwin"]:
            keyboard.press_key(keycode, is_shift=is_shift)
    except Exception:
        raise AutoControlKeyboardException(exception_tag.keyboard_press_key)


def release_key(keycode, is_shift=False):
    try:
        keycode = keys_table.get(keycode)
    except Exception:
        raise AutoControlCantFindKeyException(exception_tag.table_cant_find_key)
    try:
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            keyboard.release_key(keycode)
        elif sys.platform in ["darwin"]:
            keyboard.release_key(keycode, is_shift=is_shift)
    except Exception:
        raise AutoControlKeyboardException(exception_tag.keyboard_release_key)


def type_key(keycode, is_shift=False):
    try:
        press_key(keycode, is_shift)
        release_key(keycode, is_shift)
    except AutoControlKeyboardException:
        raise AutoControlKeyboardException(exception_tag.keyboard_type_key)


def check_key_is_press(key_code):
    if type(key_code) is int:
        get_key_code = key_code
    else :
        get_key_code = keys_table.get(key_code)
    return keyboard_listener.check_key_is_press(keycode=get_key_code)


def write(write_string, is_shift=False):
    try:
        for single_string in write_string:
            try:
                if keys_table.get(single_string) is not None:
                    type_key(single_string, is_shift)
                else:
                    raise AutoControlKeyboardException
            except AutoControlKeyboardException:
                print(exception_tag.keyboard_write_cant_find + " : " + single_string, file=sys.stderr)
    except AutoControlKeyboardException:
        raise AutoControlKeyboardException(exception_tag.keyboard_write)


def hotkey(key_code_list, is_shift=False):
    try:
        for key in key_code_list:
            press_key(key, is_shift)
        key_code_list.reverse()
        for key in key_code_list:
            release_key(key, is_shift)
    except AutoControlKeyboardException:
        raise AutoControlKeyboardException(exception_tag.keyboard_hotkey)
