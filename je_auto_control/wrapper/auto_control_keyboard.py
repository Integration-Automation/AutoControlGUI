import sys
from typing import Tuple

from je_auto_control.utils.exception.exception_tags import keyboard_hotkey
from je_auto_control.utils.exception.exception_tags import keyboard_press_key
from je_auto_control.utils.exception.exception_tags import keyboard_release_key
from je_auto_control.utils.exception.exception_tags import keyboard_type_key
from je_auto_control.utils.exception.exception_tags import keyboard_write
from je_auto_control.utils.exception.exception_tags import keyboard_write_cant_find
from je_auto_control.utils.exception.exception_tags import table_cant_find_key
from je_auto_control.utils.exception.exceptions import AutoControlCantFindKeyException
from je_auto_control.utils.exception.exceptions import AutoControlKeyboardException
from je_auto_control.utils.logging.loggin_instance import auto_control_logger
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.platform_wrapper import keyboard, special_mouse_keys_table
from je_auto_control.wrapper.platform_wrapper import keyboard_check
from je_auto_control.wrapper.platform_wrapper import keyboard_keys_table


def get_special_table() -> dict:
    return special_mouse_keys_table


def get_keyboard_keys_table() -> dict:
    return keyboard_keys_table


def press_keyboard_key(keycode: [int, str], is_shift: bool = False, skip_record: bool = False) -> str:
    """
    use to press a key still press to use release key
    or use critical exit
    return keycode
    :param keycode which keycode we want to press
    :param is_shift press shift True or False
    :param skip_record skip record on record total list True or False
    """
    auto_control_logger.info(
        f"press_keyboard_key, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}"
    )
    param = locals()
    try:
        if isinstance(keycode, str):
            try:
                keycode = keyboard_keys_table.get(keycode)
            except AutoControlCantFindKeyException:
                auto_control_logger.error(
                    f"press_keyboard_key failed, keycode: {keycode}, is_shift: {is_shift}, "
                    f"failed: {repr(AutoControlCantFindKeyException(table_cant_find_key))}"
                )
                raise AutoControlCantFindKeyException(table_cant_find_key)
        try:
            if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
                keyboard.press_key(keycode)
            elif sys.platform in ["darwin"]:
                keyboard.press_key(keycode, is_shift=is_shift)
            if skip_record is False:
                record_action_to_list("press_key", param)
            return str(keycode)
        except AutoControlKeyboardException as error:
            if skip_record is False:
                record_action_to_list("press_key", param, repr(error))
            auto_control_logger.error(
                f"press_keyboard_key failed, keycode: {keycode}, is_shift: {is_shift}, "
                f"{repr(AutoControlKeyboardException(keyboard_press_key + ' ' + repr(error)))}"
            )
            raise AutoControlKeyboardException(keyboard_press_key + " " + repr(error))
        except TypeError as error:
            if skip_record is False:
                record_action_to_list("press_key", param, repr(error))
            auto_control_logger.error(
                f"press_keyboard_key failed, keycode: {keycode}, is_shift: {is_shift}, "
                f"failed: {repr(AutoControlKeyboardException)}"
            )
            raise AutoControlKeyboardException(repr(error))
    except Exception as error:
        if skip_record is False:
            record_action_to_list("press_key", param, repr(error))
        auto_control_logger.error(
            f"press_keyboard_key failed, keycode: {keycode}, is_shift: {is_shift}, "
            f"failed: {repr(error)}"
        )


def release_keyboard_key(keycode: [int, str], is_shift: bool = False, skip_record: bool = False) -> str:
    """
    use to release pressed key return keycode
    :param keycode which keycode we want to release
    :param is_shift press shift True or False
    :param skip_record skip record on record total list True or False
    """
    auto_control_logger.info(
        f"release_keyboard_key, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}"
    )
    param = locals()
    try:
        if isinstance(keycode, str):
            try:
                keycode = keyboard_keys_table.get(keycode)
            except AutoControlCantFindKeyException:
                raise AutoControlCantFindKeyException(table_cant_find_key)
        try:
            if sys.platform in ["win32", "cygwin", "msys", "linux", "linux2"]:
                keyboard.release_key(keycode)
            elif sys.platform in ["darwin"]:
                keyboard.release_key(keycode, is_shift=is_shift)
            if skip_record is False:
                record_action_to_list("release_key", param)
            return str(keycode)
        except AutoControlKeyboardException as error:
            if skip_record is False:
                record_action_to_list("release_key", param, repr(error))
            auto_control_logger.error(
                f"release_keyboard_key, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}, "
                f"failed: {AutoControlKeyboardException(keyboard_release_key + ' ' + repr(error))}"
            )
            raise AutoControlKeyboardException(keyboard_release_key + " " + repr(error))
        except TypeError as error:
            if skip_record is False:
                record_action_to_list("release_key", param, repr(error))
            auto_control_logger.error(
                f"release_keyboard_key, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}, "
                f"failed: {AutoControlKeyboardException(error)}"
            )
            raise AutoControlKeyboardException(error)
    except Exception as error:
        if skip_record is False:
            record_action_to_list("release_key", param, repr(error))
        auto_control_logger.error(
            f"release_keyboard_key, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}, "
            f"failed: {repr(error)}"
        )


def type_keyboard(keycode: [int, str], is_shift: bool = False, skip_record: bool = False) -> str:
    """
    press and release key return keycode
    :param keycode which keycode we want to type
    :param is_shift press shift True or False
    :param skip_record skip record on record total list True or False
    """
    auto_control_logger.info(
        f"type_keyboard, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}"
    )
    param = locals()
    try:
        try:
            press_keyboard_key(keycode, is_shift, skip_record=True)
            release_keyboard_key(keycode, is_shift, skip_record=True)
            if skip_record is False:
                record_action_to_list("type_keyboard", param)
            return str(keycode)
        except AutoControlKeyboardException as error:
            if skip_record is False:
                record_action_to_list("type_keyboard", param, repr(error))
            auto_control_logger.error(
                f"type_keyboard, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}, "
                f"failed: {repr(AutoControlKeyboardException(keyboard_type_key + ' ' + repr(error)))}"
            )
            raise AutoControlKeyboardException(keyboard_type_key + " " + repr(error))
        except TypeError as error:
            if skip_record is False:
                record_action_to_list("type_keyboard", param, repr(error))
            auto_control_logger.error(
                f"type_keyboard, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}, "
                f"failed: {repr(AutoControlKeyboardException(repr(error)))}"
            )
            raise AutoControlKeyboardException(repr(error))
    except Exception as error:
        if skip_record is False:
            record_action_to_list("type_keyboard", param, repr(error))
        auto_control_logger.error(
            f"type_keyboard, keycode: {keycode}, is_shift: {is_shift}, skip_record: {skip_record}, "
            f"failed: {repr(error)}"
        )


def check_key_is_press(keycode: [int, str]) -> bool:
    """
    use to check key is press return True or False
    :param keycode check key is press or not
    """
    auto_control_logger.info(
        f"check_key_is_press, keycode: {keycode}"
    )
    param = locals()
    try:
        if isinstance(keycode, int):
            get_key_code = keycode
        else:
            get_key_code = keyboard_keys_table.get(keycode)
        record_action_to_list("check_key_is_press", param)
        return keyboard_check.check_key_is_press(keycode=get_key_code)
    except Exception as error:
        record_action_to_list("check_key_is_press", param, repr(error))
        auto_control_logger.error(
            f"check_key_is_press, keycode: {keycode}, "
            f"failed: {repr(error)}"
        )


def write(write_string: str, is_shift: bool = False) -> str:
    """
    use to press and release whole we get this function str
    return all press and release str
    :param write_string while string not on write_string+1 type_keyboard(string)
    :param is_shift press shift True or False
    """
    auto_control_logger.info(
        f"write, write_string: {write_string}, is_shift: {is_shift}"
    )
    param = locals()
    try:
        try:
            record_write_string = ""
            for single_string in write_string:
                try:
                    key = keyboard_keys_table.get(single_string, None)
                    if key is not None:
                        record_write_string = "".join(
                            [
                                record_write_string,
                                type_keyboard(key, is_shift, skip_record=True)
                            ]
                        )
                    elif single_string.isspace():
                        record_write_string = "".join(
                            [
                                record_write_string,
                                type_keyboard("space", is_shift, skip_record=True)
                            ]
                        )
                    else:
                        auto_control_logger.error(
                            f"write, write_string: {write_string}, is_shift: {is_shift}, "
                            f"failed: {AutoControlKeyboardException(keyboard_write_cant_find)}"
                        )
                        raise AutoControlKeyboardException(keyboard_write_cant_find)
                except AutoControlKeyboardException as error:
                    auto_control_logger.error(
                        f"write, write_string: {write_string}, is_shift: {is_shift}, "
                        f"failed: {repr(error)}, keyboard_write_cant_find, {single_string}"
                    )
                    raise AutoControlKeyboardException(keyboard_write_cant_find)
            record_action_to_list("write", param)
            return record_write_string
        except AutoControlKeyboardException as error:
            auto_control_logger.error(
                f"write, write_string: {write_string}, is_shift: {is_shift}, "
                f"failed: {AutoControlKeyboardException(keyboard_write + ' ' + repr(error))}"
            )
            raise AutoControlKeyboardException(keyboard_write + " " + repr(error))
    except Exception as error:
        record_action_to_list("write", param, repr(error))
        auto_control_logger.error(
            f"write, write_string: {write_string}, is_shift: {is_shift}, "
            f"failed: {repr(error)}"
        )


def hotkey(key_code_list: list, is_shift: bool = False) -> Tuple[str, str]:
    """
    use to press and release all key on key_code_list
    then reverse list press and release again
    return [press_str_list, release_str_list]
    :param key_code_list press and release all key on list and reverse
    :param is_shift press shift True or False
    """
    auto_control_logger.info(
        f"hotkey, key_code_list: {key_code_list}, is_shift: {is_shift}"
    )
    param = locals()
    try:
        try:
            record_hotkey_press_string = ""
            record_hotkey_release_string = ""
            for key in key_code_list:
                record_hotkey_press_string = ",".join(
                    [
                        record_hotkey_press_string,
                        press_keyboard_key(key, is_shift, skip_record=True)
                    ]
                )
            key_code_list.reverse()
            for key in key_code_list:
                record_hotkey_release_string = ",".join(
                    [
                        record_hotkey_release_string,
                        release_keyboard_key(key, is_shift, skip_record=True)
                    ]
                )
            record_action_to_list("hotkey", param)
            return record_hotkey_press_string, record_hotkey_release_string
        except AutoControlKeyboardException as error:
            auto_control_logger.error(
                f"hotkey, key_code_list: {key_code_list}, is_shift: {is_shift}, "
                f"failed: {AutoControlKeyboardException(keyboard_hotkey + ' ' + repr(error))}"
            )
            raise AutoControlKeyboardException(keyboard_hotkey + " " + repr(error))
    except Exception as error:
        record_action_to_list("hotkey", param, repr(error))
        auto_control_logger.error(
            f"hotkey, key_code_list: {key_code_list}, is_shift: {is_shift}, "
            f"failed: {repr(error)}"
        )
