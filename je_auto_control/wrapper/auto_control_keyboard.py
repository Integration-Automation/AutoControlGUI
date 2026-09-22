"""Keyboard API: key table, press / release / type, ``write``, hotkeys, state.

The platform branches follow the rule written out at the top of
``auto_control_mouse``: ask ``platform_id`` which input stack this is instead
of listing OS names (a literal list left the BSDs outside every branch, typing
nothing and reporting success), spell the macOS test as
``sys.platform == "darwin"`` because it is the branch whose signature differs
and the only form a type checker can prune, and raise on a platform that
matches neither.
"""
import sys
import warnings
from typing import Optional, Union, Tuple

from je_auto_control.utils.exception.exception_tags import (
    keyboard_press_key_error_message, keyboard_release_key_error_message,
    keyboard_type_key_error_message, table_cant_find_key_error_message,
    keyboard_write_cant_find_error_message, keyboard_write_error_message,
    keyboard_hotkey_error_message,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlCantFindKeyException, AutoControlKeyboardException
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.platform_id import is_windows, is_x11_unix
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.utils.text_unicode.text_unicode import unicode_code_units
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
        # 分支寫法與理由見模組 docstring：非 macOS 問輸入堆疊（BSD 曾經
        # 落在所有分支之外），macOS 用字面比較（型別檢查器剪得掉）。
        # Branch spelling explained in the module docstring.
        if sys.platform == "darwin":
            keyboard.press_key(keycode, is_shift=is_shift)
        elif is_windows() or is_x11_unix():
            keyboard.press_key(keycode)
        else:
            raise AutoControlKeyboardException(
                f"press_keyboard_key: no backend for {sys.platform!r}")

        if not skip_record:
            record_action_to_list("press_key", {"keycode": keycode, "is_shift": is_shift})
        return str(keycode)

    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        if not skip_record:
            record_action_to_list("press_key", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"press_keyboard_key failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_press_key_error_message} {repr(error)}") from error


def release_keyboard_key(keycode: Union[int, str], is_shift: bool = False,
                         skip_record: bool = False) -> Optional[str]:
    """
    放開指定鍵
    Release a keyboard key
    """
    autocontrol_logger.info(f"release_keyboard_key, keycode={keycode}, is_shift={is_shift}, skip_record={skip_record}")
    try:
        keycode = _resolve_keycode(keycode)
        # 分支寫法與理由見模組 docstring：非 macOS 問輸入堆疊（BSD 曾經
        # 落在所有分支之外），macOS 用字面比較（型別檢查器剪得掉）。
        # Branch spelling explained in the module docstring.
        if sys.platform == "darwin":
            keyboard.release_key(keycode, is_shift=is_shift)
        elif is_windows() or is_x11_unix():
            keyboard.release_key(keycode)
        else:
            raise AutoControlKeyboardException(
                f"release_keyboard_key: no backend for {sys.platform!r}")

        if not skip_record:
            record_action_to_list("release_key", {"keycode": keycode, "is_shift": is_shift})
        return str(keycode)

    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        if not skip_record:
            record_action_to_list("release_key", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"release_keyboard_key failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_release_key_error_message} {repr(error)}") from error


def _release_still_held(still_held: list, is_shift: bool) -> None:
    """把「已經按下去、還沒放開」的鍵**倒著**放開。清空 ``still_held``。
    Release keys that are still held down, in reverse order.

    這支跑在 ``finally`` 裡，所以**絕不往外拋**：清理路徑再丟一個例外只會把原本
    那個蓋掉，而使用者真正需要看到的是原因。放不開就記一行 error 繼續處理下一個
    ——放開三個鍵時第一個失敗，不該讓另外兩個也留在按下狀態。
    This runs from ``finally`` and therefore never raises: an exception here
    would replace the original one, which is what the caller actually needs.

    收 ``Exception`` 而不是那份 ``(OSError, RuntimeError, …)`` 名單，是因為
    ``release_keyboard_key`` 丟的是 ``AutoControlKeyboardException``，它屬於
    ``AutoControlException`` 家族——不在那份名單裡的任何一項底下。
    """
    while still_held:
        key = still_held.pop()
        try:
            release_keyboard_key(key, is_shift, skip_record=True)
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: see docstring
            autocontrol_logger.error(
                f"failed to release a still-held key {key!r}: {repr(error)}")


def type_keyboard(keycode: Union[int, str], is_shift: bool = False,
                  skip_record: bool = False) -> Optional[str]:
    """
    模擬輸入 (按下再放開)
    Type a keyboard key (press and release)

    按下與放開之間的任何失敗都**不可以**把鍵留在按下狀態——那是使用者真實的鍵盤：
    一個卡住的 Ctrl 或 Alt 會讓後面每一次點選、每一次按鍵都變成別的意思，而且畫面上
    沒有任何跡象。所以放開走 ``finally``，不是走 ``except``。
    A failure between press and release must never leave the key down: this is
    the user's real keyboard, and a stuck modifier silently changes the meaning
    of every subsequent click and keystroke.
    """
    autocontrol_logger.info(f"type_keyboard, keycode={keycode}, is_shift={is_shift}, skip_record={skip_record}")
    still_held: list = []
    try:
        press_keyboard_key(keycode, is_shift, skip_record=True)
        still_held.append(keycode)
        release_keyboard_key(keycode, is_shift, skip_record=True)
        still_held.clear()

        if not skip_record:
            record_action_to_list("type_keyboard", {"keycode": keycode, "is_shift": is_shift})
        return str(keycode)

    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        if not skip_record:
            record_action_to_list("type_keyboard", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"type_keyboard failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_type_key_error_message} {repr(error)}") from error
    finally:
        # **為什麼是 `finally` 而不是加進上面的 `except`**：`press_keyboard_key` 與
        # `release_keyboard_key` 丟的是 `AutoControlKeyboardException`，它屬於
        # `AutoControlException` 家族、**不在**那份 `(OSError, RuntimeError, AttributeError,
        # TypeError, ValueError)` 名單的任何一項底下（實測確認）。也就是說最可能
        # 發生的失敗（鍵名不在對照表裡、平台不支援、後端出錯）根本走不到那個
        # `except`。`finally` 是唯一每條離開路徑都會跑到的地方。
        _release_still_held(still_held, is_shift)

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
        if get_key_code is None:
            # 表裡沒有這個鍵名。原本會把 None 送進後端，讓它自己去炸——
            # Windows 後端會 TypeError，X11 後端則是安靜地回 False。
            # A key name the table has no entry for used to be handed to the
            # backend as None: a TypeError on Windows, a silent False on X11.
            autocontrol_logger.error(
                f"check_key_is_press: {table_cant_find_key_error_message}, keycode={keycode}")
            return None
        record_action_to_list("check_key_is_press", {"keycode": keycode})
        return keyboard_check.check_key_is_press(keycode=get_key_code)
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("check_key_is_press", {"keycode": keycode}, repr(error))
        autocontrol_logger.error(f"check_key_is_press failed: {repr(error)}")
        return None


# Whitespace that means a *key*, not a character. Sent as a Unicode code point
# these are silently dropped by most applications — a newline especially, which
# turns a multi-line `write` into one run-on line with nothing reported.
WRITE_CONTROL_KEYS = {"\n": "return", "\r": "return", "\t": "tab",
                      "\b": "back"}


def _write_char_via_unicode(single_char: str) -> bool:
    """
    以 Unicode 事件輸入單一字元 (鍵盤對應表沒有的字元)
    Type one character the virtual-key table has no entry for

    :param single_char: 單一字元 One character
    :return: 是否成功送出 Whether the backend could send it
    """
    type_unicode_unit = getattr(keyboard, "type_unicode_unit", None)
    if not callable(type_unicode_unit):
        return False
    for unit in unicode_code_units(single_char):
        type_unicode_unit(unit)
    return True


def write(write_string: str, is_shift: bool = False) -> Optional[str]:
    """
    模擬輸入整個字串
    Type a whole string

    The virtual-key table covers barely 192 keys, so a literal reading of it
    cannot type ``, . / : ? ! _ + @ %`` on a US layout, nor any CJK or accented
    character. Characters it lacks fall back to Unicode key events where the
    backend supports them, and only raise where it does not — otherwise a single
    comma fails the whole string.

    :param write_string: 要輸入的字串 String to type
    :param is_shift: 是否同時按下 Shift
    :return: 輸入的字串
    """
    autocontrol_logger.info(f"write, write_string={write_string}, is_shift={is_shift}")
    try:
        record_write_chars = []
        for single_char in write_string:
            key = keyboard_keys_table.get(single_char)
            control_key = WRITE_CONTROL_KEYS.get(single_char)
            if control_key is not None and control_key in keyboard_keys_table:
                # Before the table lookup: a newline must press Enter, not type
                # U+000A and not fall through to the space fallback below.
                type_keyboard(control_key, is_shift, skip_record=True)
            elif key is not None:
                type_keyboard(key, is_shift, skip_record=True)
            elif _write_char_via_unicode(single_char):
                pass
            elif single_char.isspace():
                type_keyboard("space", is_shift, skip_record=True)
            else:
                autocontrol_logger.error(f"write failed: {keyboard_write_cant_find_error_message}, char={single_char}")
                raise AutoControlKeyboardException(keyboard_write_cant_find_error_message)
            record_write_chars.append(single_char)

        result = "".join(record_write_chars)
        record_action_to_list("write", {"write_string": write_string, "is_shift": is_shift})
        return result

    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("write", {"write_string": write_string}, repr(error))
        autocontrol_logger.error(f"write failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_write_error_message} {repr(error)}") from error


def hotkey(key_code_list: list, is_shift: bool = False) -> Tuple[str, str]:
    """
    模擬組合鍵 (依序按下，再反向放開)
    Simulate hotkey (press all keys, then release in reverse order)

    :param key_code_list: 鍵盤代碼清單 List of keycodes
    :param is_shift: 是否同時按下 Shift
    :return: (press_str, release_str)
    """
    autocontrol_logger.info(f"hotkey, key_code_list={key_code_list}, is_shift={is_shift}")
    # 已經按下去、還沒放開的鍵，**依按下的順序**。放開時倒著走。
    still_held: list = []
    try:
        press_list = []
        release_list = []

        for key in key_code_list:
            press_list.append(press_keyboard_key(key, is_shift, skip_record=True))
            # 按成功了才記——`press_keyboard_key` 丟例外時那個鍵並沒有被按下去，
            # 記進來的話收尾會去放開一個從來沒按下的鍵。
            still_held.append(key)

        for key in reversed(key_code_list):
            release_list.append(release_keyboard_key(key, is_shift, skip_record=True))
            # 放開的順序與 `still_held` 的堆疊順序一致（都是反序），所以 `pop()`
            # 拿到的必定就是剛放開的那一個——同一個鍵重複出現在清單裡也對。
            still_held.pop()

        press_str = ",".join(filter(None, press_list))
        release_str = ",".join(filter(None, release_list))

        record_action_to_list("hotkey", {"keys": key_code_list, "is_shift": is_shift})
        return press_str, release_str

    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("hotkey", {"keys": key_code_list}, repr(error))
        autocontrol_logger.error(f"hotkey failed: {repr(error)}")
        raise AutoControlKeyboardException(f"{keyboard_hotkey_error_message} {repr(error)}") from error
    finally:
        # 組合鍵是這個缺陷**最貴**的形態：`hotkey(["ctrl", "shift", "esc"])` 在第三
        # 個鍵上失敗，就會把 Ctrl 與 Shift 留在按下狀態——使用者真實的鍵盤上，之後
        # 每一次點選與按鍵都變成別的意思，而畫面上沒有任何跡象。
        # 為什麼是 `finally` 不是 `except`：見 `type_keyboard` 的同名說明
        # （`AutoControlKeyboardException` 不在那份 except 名單的任何一項底下）。
        _release_still_held(still_held, is_shift)

def send_key_event_to_window(window_title: str, keycode: Union[int, str]) -> None:
    """
    將鍵盤事件送到指定視窗（**已棄用**，改用 ``post_key_to_window``）
    Send a key event to a specific window. **Deprecated** — use
    ``je_auto_control.post_key_to_window``.

    這支原本把訊息投遞給**頂層視窗**，但鍵盤訊息是送給**有焦點的子控制項**的，
    所以對任何有子控制項的程式都等於什麼都沒做——而且照樣回報成功。實測（字元
    對應表）：投遞給外框，一個字都沒進去；投遞給焦點控制項，字就進去了。現在
    轉呼叫 ``post_key_to_window``，行為因此**改變**（會真的作用），並發出
    ``DeprecationWarning``。視窗標題也跟著改成**片段比對**，與其餘視窗函式一致。

    This posted to the top-level frame, but keyboard messages go to the control
    that *has focus*: it silently did nothing in any application with child
    controls while still reporting success. It now delegates to
    ``post_key_to_window``, so the behaviour changes — it works — and the title
    is matched as a substring like every other window function.

    :param window_title: 視窗標題片段 Window title substring
    :param keycode: 鍵盤代碼或字串 Keycode or string
    """
    warnings.warn(
        "send_key_event_to_window is deprecated; use post_key_to_window. The "
        "old implementation posted to the top-level frame and silently did "
        "nothing for windows with child controls.",
        DeprecationWarning, stacklevel=2,
    )
    autocontrol_logger.info(f"send_key_event_to_window, window={window_title}, keycode={keycode}")
    if sys.platform == "darwin":
        return
    from je_auto_control.wrapper.auto_control_window import post_key_to_window
    try:
        posted = post_key_to_window(window_title, keycode)
        record_action_to_list(
            "send_key_event_to_window",
            {"window_title": window_title, "keycode": keycode, "posted": posted})
    except Exception as error:  # noqa: BLE001  # reason: preserved contract, never raises
        record_action_to_list(
            "send_key_event_to_window",
            {"window_title": window_title, "keycode": keycode}, repr(error))
        autocontrol_logger.error(
            f"send_key_event_to_window failed, window={window_title}, keycode={keycode}, error={repr(error)}"
        )
