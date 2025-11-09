import sys

from je_auto_control.utils.exception.exception_tags import osx_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

import AppKit
import Quartz

from je_auto_control.osx.core.utils.osx_vk import osx_key_shift

# === 特殊鍵對照表 Special key mapping ===
special_key_table = {
    "key_sound_up": 0,
    "key_sound_down": 1,
    "key_brightness_up": 2,
    "key_brightness_down": 3,
    "key_capslock": 4,
    "key_help": 5,
    "key_power": 6,
    "key_mute": 7,
    "key_arrow_up": 8,
    "key_arrow_down": 9,
    "key_numlock": 10,
    "key_contrast_up": 11,
    "key_contrast_down": 12,
    "key_launch_panel": 13,
    "key_eject": 14,
    "key_vidmirror": 15,
    "key_play": 16,
    "key_next": 17,
    "key_previous": 18,
    "key_fast": 19,
    "key_rewind": 20,
    "key_illumination_up": 21,
    "key_illumination_down": 22,
    "key_illumination_toggle": 23,
}


def normal_key(keycode: int, is_shift: bool, is_down: bool) -> None:
    """
    Simulate normal key press/release
    模擬普通鍵盤按下/釋放

    :param keycode: 要模擬的鍵盤代碼
    :param is_shift: 是否同時按下 Shift
    :param is_down: True = 按下, False = 釋放
    """
    try:
        # 如果需要 Shift，先送出 Shift 事件
        if is_shift:
            event = Quartz.CGEventCreateKeyboardEvent(
                None,
                osx_key_shift,
                is_down
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

        # 送出目標鍵盤事件
        event = Quartz.CGEventCreateKeyboardEvent(
            None,
            keycode,
            is_down
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    except ValueError as error:
        print(repr(error), file=sys.stderr)


def special_key(keycode: str, is_shift: bool) -> None:
    """
    Simulate special key press/release
    模擬特殊鍵盤按下/釋放 (例如音量、亮度、播放鍵)

    :param keycode: 特殊鍵名稱 (必須存在於 special_key_table)
    :param is_shift: 是否同時按下 Shift
    """
    if keycode not in special_key_table:
        raise ValueError(f"Unknown special key: {keycode}")

    mapped_code = special_key_table[keycode]

    event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2(
        Quartz.NSSystemDefined,
        (0, 0),
        0xa00 if is_shift else 0xb00,
        0,
        0,
        0,
        8,
        (mapped_code << 16) | ((0xa if is_shift else 0xb) << 8),
        -1
    )
    Quartz.CGEventPost(0, event)


def press_key(keycode: int | str, is_shift: bool) -> None:
    """
    Press a key (normal or special)
    模擬按下鍵盤按鍵 (普通或特殊)

    :param keycode: 鍵盤代碼或特殊鍵名稱
    :param is_shift: 是否同時按下 Shift
    """
    if keycode in special_key_table:
        special_key(keycode, is_shift)
    else:
        normal_key(keycode, is_shift, True)


def release_key(keycode: int | str, is_shift: bool) -> None:
    """
    Release a key (normal or special)
    模擬釋放鍵盤按鍵 (普通或特殊)

    :param keycode: 鍵盤代碼或特殊鍵名稱
    :param is_shift: 是否同時按下 Shift
    """
    if keycode in special_key_table:
        special_key(keycode, is_shift)
    else:
        normal_key(keycode, is_shift, False)