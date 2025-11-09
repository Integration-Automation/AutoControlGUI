import sys
from typing import Optional, Union, Tuple

from je_auto_control.utils.exception.exception_tags import (
    keyboard_press_key_error_message, keyboard_release_key_error_message, keyboard_type_key_error_message,
    table_cant_find_key_error_message, keyboard_write_cant_find_error_message, keyboard_write_error_message, keyboard_hotkey_error_message
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlCantFindKeyException, AutoControlKeyboardException
)
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import keyboard, keyboard_keys_table, keyboard_check

def get_keyboard_keys_table() -> dict:
    """
    取得鍵盤對應表
    Get keyboard keys table
    """
    return keyboard_keys_table


def _resolve_keycode(keycode: Union[int, str]) -> int:
    """
    將字串鍵名轉換成對應的 keycode
    Resolve string key name to keycode
    """
    if isinstance(keycode, str):
        resolved = keyboard_keys_table.get(keycode)
        if resolved is None:
            raise AutoControlCantFindKeyException(table_cant_find_key_error_message)
        return resolved
    return keycode


def press_keyboard_key(keycode: Union[int, str], is_shift: bool = False,
                       skip_record: bool = False) -> Optional[str]:
    """
    按下指定鍵
    Press a keyboard key

    :param keycode: 鍵盤代碼或字串 Keycode or string
    :param is_shift: 是否同時按下 Shift
    :param skip_record: 是否跳過紀錄
    :return: keycode 字串
    """
    autocontrol_logger.info(f"press_keyboard_key, keycode={keycode}, is_shift={is_shift}, skip_record={skip_record}")
    try:
        keycode = _resolve_keycode(keycode)
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            keyboard.press_key(keycode)
        elif sys.platform == "darwin":
            keyboard.press_key(keycode, is_shift=is_shift)

        if not skip_record:
            record_action_to_list("press_key", {"keycode": keycode, "is_shift": is_shift})
        return str(keycode)

    except Exception as error:
        if not skip_record:
            record_action_to_list("press_key", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"press_keyboard_key failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_press_key_error_message} {repr(error)}")


def release_keyboard_key(keycode: Union[int, str], is_shift: bool = False,
                         skip_record: bool = False) -> Optional[str]:
    """
    放開指定鍵
    Release a keyboard key
    """
    autocontrol_logger.info(f"release_keyboard_key, keycode={keycode}, is_shift={is_shift}, skip_record={skip_record}")
    try:
        keycode = _resolve_keycode(keycode)
        if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
            keyboard.release_key(keycode)
        elif sys.platform == "darwin":
            keyboard.release_key(keycode, is_shift=is_shift)

        if not skip_record:
            record_action_to_list("release_key", {"keycode": keycode, "is_shift": is_shift})
        return str(keycode)

    except Exception as error:
        if not skip_record:
            record_action_to_list("release_key", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"release_keyboard_key failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_release_key_error_message} {repr(error)}")


def type_keyboard(keycode: Union[int, str], is_shift: bool = False,
                  skip_record: bool = False) -> Optional[str]:
    """
    模擬輸入 (按下再放開)
    Type a keyboard key (press and release)
    """
    autocontrol_logger.info(f"type_keyboard, keycode={keycode}, is_shift={is_shift}, skip_record={skip_record}")
    try:
        press_keyboard_key(keycode, is_shift, skip_record=True)
        release_keyboard_key(keycode, is_shift, skip_record=True)

        if not skip_record:
            record_action_to_list("type_keyboard", {"keycode": keycode, "is_shift": is_shift})
        return str(keycode)

    except Exception as error:
        if not skip_record:
            record_action_to_list("type_keyboard", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"type_keyboard failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_type_key_error_message} {repr(error)}")

def check_key_is_press(keycode: Union[int, str]) -> Optional[bool]:
    """
    檢查某個鍵是否正在被按下
    Check if a key is currently pressed

    :param keycode: 鍵盤代碼或字串 Keycode or string
    :return: True / False / None
    """
    autocontrol_logger.info(f"check_key_is_press, keycode={keycode}")
    try:
        get_key_code = keycode if isinstance(keycode, int) else keyboard_keys_table.get(keycode)
        record_action_to_list("check_key_is_press", {"keycode": keycode})
        return keyboard_check.check_key_is_press(keycode=get_key_code)
    except Exception as error:
        record_action_to_list("check_key_is_press", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"check_key_is_press failed: {repr(error)}")
        return None


def write(write_string: str, is_shift: bool = False) -> Optional[str]:
    """
    模擬輸入整個字串
    Type a whole string

    :param write_string: 要輸入的字串 String to type
    :param is_shift: 是否同時按下 Shift
    :return: 輸入的字串
    """
    autocontrol_logger.info(f"write, write_string={write_string}, is_shift={is_shift}")
    try:
        record_write_chars = []
        for single_char in write_string:
            key = keyboard_keys_table.get(single_char)
            if key is not None:
                record_write_chars.append(type_keyboard(key, is_shift, skip_record=True))
            elif single_char.isspace():
                record_write_chars.append(type_keyboard("space", is_shift, skip_record=True))
            else:
                autocontrol_logger.error(f"write failed: {keyboard_write_cant_find_error_message}, char={single_char}")
                raise AutoControlKeyboardException(keyboard_write_cant_find_error_message)

        result = "".join(record_write_chars)
        record_action_to_list("write", {"write_string": write_string, "is_shift": is_shift})
        return result

    except Exception as error:
        record_action_to_list("write", {"write_string": write_string}, repr(error))
        autocontrol_logger.error(f"write failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_write_error_message} {repr(error)}")


def hotkey(key_code_list: list, is_shift: bool = False) -> Optional[Tuple[str, str]]:
    """
    模擬組合鍵 (依序按下，再反向放開)
    Simulate hotkey (press all keys, then release in reverse order)

    :param key_code_list: 鍵盤代碼清單 List of keycodes
    :param is_shift: 是否同時按下 Shift
    :return: (press_str, release_str)
    """
    autocontrol_logger.info(f"hotkey, key_code_list={key_code_list}, is_shift={is_shift}")
    try:
        press_list = []
        release_list = []

        for key in key_code_list:
            press_list.append(press_keyboard_key(key, is_shift, skip_record=True))

        for key in reversed(key_code_list):
            release_list.append(release_keyboard_key(key, is_shift, skip_record=True))

        press_str = ",".join(filter(None, press_list))
        release_str = ",".join(filter(None, release_list))

        record_action_to_list("hotkey", {"keys": key_code_list, "is_shift": is_shift})
        return press_str, release_str

    except Exception as error:
        record_action_to_list("hotkey", {"keys": key_code_list}, repr(error))
        autocontrol_logger.error(f"hotkey failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_hotkey_error_message} {repr(error)}")

def send_key_event_to_window(window_title: str, keycode: Union[int, str]) -> None:
    """
    將鍵盤事件送到指定視窗
    Send a key event to a specific window

    :param window_title: 視窗標題 Window title
    :param keycode: 鍵盤代碼或字串 Keycode or string
    """
    autocontrol_logger.info(f"send_key_event_to_window, window={window_title}, keycode={keycode}")
    try:
        # macOS 不支援直接送鍵盤事件
        if sys.platform == "darwin":
            return

        # 解析 keycode Resolve keycode
        if isinstance(keycode, int):
            get_key_code = keycode
        else:
            get_key_code = keyboard_keys_table.get(keycode)
            if get_key_code is None:
                raise AutoControlKeyboardException(f"Key not found: {keycode}")

        # 呼叫底層 API Send event
        keyboard.send_key_event_to_window(window_title, keycode=get_key_code)

        # 紀錄動作 Record action
        record_action_to_list("send_key_event_to_window", {"window_title": window_title, "keycode": get_key_code})

    except Exception as error:
        record_action_to_list("send_key_event_to_window", {"window_title": window_title, "keycode": keycode}, repr(error))
        autocontrol_logger.error(
            f"send_key_event_to_window failed, window={window_title}, keycode={keycode}, error={repr(error)}"
        )