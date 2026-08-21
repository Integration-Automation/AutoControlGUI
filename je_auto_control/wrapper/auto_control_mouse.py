"""Mouse API: position, press / release / click, scroll, deprecated posting.

**How the platform branches in this file are written**, because both spellings
here are load-bearing and neither is arbitrary:

* Everything that is not macOS asks ``platform_id`` *which input stack* this
  is — ``is_windows() or is_x11_unix()`` — rather than listing OS names. The
  list this replaced, ``["win32", "cygwin", "msys", "linux", "linux2"]``, left
  the BSDs outside every branch: a FreeBSD desktop is an ordinary X11 desktop,
  so the call fell off the end, raised nothing, did nothing, and still reported
  success. ``mouse_scroll`` was fixed first; the press/release pair carried the
  same hole until the seam was typed.
* macOS is spelled ``sys.platform == "darwin"`` rather than ``is_macos()``.
  The two are the same test by definition, but only the literal is one a type
  checker can resolve, and macOS is the branch whose *signature* differs — it
  takes ``(x, y, button)`` where the others take the button alone. Pruning that
  branch is what a per-platform backend protocol will need; see
  ``wrapper/backend_contract.py`` and ``Progress.md``.
* An OS that matches neither raises rather than returning as if it worked.
  ``platform_wrapper`` refuses such a platform at import, so this is the
  belt-and-braces half of the same statement.
"""
import ctypes
import sys
import warnings
from typing import Optional, Tuple, Union

from je_auto_control.utils.exception.exception_tags import (
    mouse_click_mouse_error_message, mouse_get_position_error_message, mouse_press_mouse_error_message,
    mouse_release_mouse_error_message, mouse_scroll_error_message, mouse_set_position_error_message,
    mouse_wrong_value_error_message, table_cant_find_key_error_message
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlCantFindKeyException, AutoControlMouseException
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.platform_id import (
    is_macos, is_windows, is_x11_unix
)
from je_auto_control.utils.test_record.record_test_class import record_action_to_list
from je_auto_control.wrapper.auto_control_screen import screen_size
from je_auto_control.wrapper.backend_contract import MouseKeycode
from je_auto_control.wrapper.platform_wrapper import mouse, mouse_keys_table, special_mouse_keys_table


def get_mouse_table() -> dict:
    """
    取得滑鼠按鍵對應表
    Get mouse keys table
    """
    return mouse_keys_table


def mouse_preprocess(mouse_keycode: Union[int, str], x: Optional[int],
                     y: Optional[int]) -> Tuple[MouseKeycode, int, int]:
    """
    前置處理：檢查 keycode 並補齊座標
    Preprocess mouse keycode and coordinates

    :param mouse_keycode: 滑鼠按鍵代碼或字串 Mouse keycode or string
    :param x: X 座標，None 代表沿用目前游標位置
    :param y: Y 座標，None 代表沿用目前游標位置
    :return: (keycode, x, y)
    """
    keycode: MouseKeycode = mouse_keycode
    try:
        if isinstance(mouse_keycode, str):
            keycode = mouse_keys_table.get(mouse_keycode)
            if keycode is None:
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
            position = get_mouse_position()
            if position is None:
                # 後端回報不出游標位置。原本這裡會在解包時拋 TypeError，
                # 而 TypeError 不是這支承諾的例外型別。
                # The backend could not report the cursor: this used to raise
                # TypeError from the unpacking, which is not the exception
                # this function promises.
                raise AutoControlMouseException(mouse_get_position_error_message)
            now_x, now_y = position
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
    return keycode, int(x), int(y)


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


def press_mouse(mouse_keycode: Union[int, str], x: Optional[int] = None,
                y: Optional[int] = None) -> tuple[MouseKeycode, int, int] | None:
    """
    按下滑鼠按鍵
    Press mouse button

    :return: (keycode, x, y)
    """
    autocontrol_logger.info(f"press_mouse, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"keycode": mouse_keycode, "x": x, "y": y}
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        # 分支寫法與理由見模組 docstring：非 macOS 問輸入堆疊（BSD 曾經
        # 落在所有分支之外），macOS 用字面比較（型別檢查器剪得掉）。
        # Branch spelling explained in the module docstring.
        if sys.platform == "darwin":
            mouse.press_mouse(x, y, mouse_keycode)
        elif is_windows() or is_x11_unix():
            mouse.press_mouse(mouse_keycode)
        else:
            raise AutoControlMouseException(
                f"press_mouse: no backend for {sys.platform!r}")
        record_action_to_list("press_mouse", param)
        return mouse_keycode, x, y
    except AutoControlMouseException as error:
        autocontrol_logger.error(f"press_mouse failed: {repr(error)}")
        raise AutoControlMouseException(mouse_press_mouse_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("press_mouse", param, repr(error))
        autocontrol_logger.error(f"press_mouse failed: {repr(error)}")
        raise


def release_mouse(mouse_keycode: Union[int, str], x: Optional[int] = None,
                  y: Optional[int] = None) -> tuple[MouseKeycode, int, int] | None:
    """
    放開滑鼠按鍵
    Release mouse button

    :return: (keycode, x, y)
    """
    autocontrol_logger.info(f"release_mouse, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"keycode": mouse_keycode, "x": x, "y": y}
    try:
        mouse_keycode, x, y = mouse_preprocess(mouse_keycode, x, y)
        # 分支寫法與理由見模組 docstring：非 macOS 問輸入堆疊（BSD 曾經
        # 落在所有分支之外），macOS 用字面比較（型別檢查器剪得掉）。
        # Branch spelling explained in the module docstring.
        if sys.platform == "darwin":
            mouse.release_mouse(x, y, mouse_keycode)
        elif is_windows() or is_x11_unix():
            mouse.release_mouse(mouse_keycode)
        else:
            raise AutoControlMouseException(
                f"release_mouse: no backend for {sys.platform!r}")
        record_action_to_list("release_mouse", param)
        return mouse_keycode, x, y
    except AutoControlMouseException as error:
        autocontrol_logger.error(f"release_mouse failed: {repr(error)}")
        raise AutoControlMouseException(mouse_release_mouse_error_message + " " + repr(error)) from error
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError) as error:
        record_action_to_list("release_mouse", param, repr(error))
        autocontrol_logger.error(f"release_mouse failed: {repr(error)}")
        raise


def click_mouse(mouse_keycode: Union[int, str], x: Optional[int] = None,
                y: Optional[int] = None) -> Tuple[MouseKeycode, int, int]:
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


def _scroll_to(x: Optional[int], y: Optional[int]) -> None:
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
    # 兩個座標都給定時不會被讀到，見下面的三元運算。
    # Never read when both coordinates were supplied.
    now_x, now_y = 0, 0
    if x is None or y is None:
        try:
            position = get_mouse_position()
        except (AutoControlMouseException, NotImplementedError, OSError):
            # 後端無法回報游標(如 Wayland 會拋 NotImplementedError)時,無法
            # 補上缺漏的座標軸,直接略過預先移動,讓滾動發生在目前游標處,
            # 而非讓例外逸出 API 承諾的降級行為。
            # Backend can't report the cursor (Wayland raises NotImplementedError);
            # without it the omitted axis can't be filled, so skip the pre-move and
            # scroll at the current cursor instead of escaping the documented
            # graceful degradation.
            return
        if position is None:
            # 同上：回報不出來就別動游標，不要在解包時炸掉整支滾動。
            # Same answer for a backend that returns no position at all.
            return
        now_x, now_y = position
    target_x = now_x if x is None else max(0, min(x, width - 1))
    target_y = now_y if y is None else max(0, min(y, height - 1))
    set_mouse_position(target_x, target_y)


def mouse_scroll(scroll_value: int, x: Optional[int] = None,
                 y: Optional[int] = None,
                 scroll_direction: str = "scroll_down"
                 ) -> Tuple[int, Union[int, str]]:
    """
    模擬滑鼠滾輪操作
    Simulate mouse scroll

    每個平台的規則相同：``scroll_value`` 為負就反向，絕對值是滾動格數。
    The sign of ``scroll_value`` reverses the direction on every platform, so a
    call written on one works on the others. X11 and Wayland used to discard it
    and always scroll ``scroll_direction``, which meant portable code scrolled
    the opposite way there with no error and no warning.

    :param scroll_value: 滾動數值，負數代表反向 Scroll value; negative reverses
    :param x: X 座標，指定時會先將游標移到該處 X position; the cursor moves here first
    :param y: Y 座標，指定時會先將游標移到該處 Y position; the cursor moves here first
    :param scroll_direction: 未帶負號時的方向，只有 X11／Wayland 後端會讀。
        The direction a *positive* count scrolls in. Only the X11 and Wayland
        backends read it — Windows and macOS have a single wheel axis and take
        the direction from the sign alone.
    :return: (scroll_value, scroll_direction)，X11／Wayland 回的是換算後的
        軸代碼，其餘平台回原字串。
        On X11 and Wayland the direction comes back as the backend axis code
        the name resolved to; elsewhere it is the name that was passed in.
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

        # 用 platform_id 問「哪一種輸入堆疊」，而不是再列一次 OS 名單：
        # 原本的 ["linux", "linux2"] 把 BSD 漏在所有分支之外，滾動在
        # FreeBSD 上不會報錯，只是什麼都不做。
        # Ask platform_id which input stack this is rather than spelling out
        # another list of OS names: the ["linux", "linux2"] one left the BSDs
        # outside every branch, so scrolling on FreeBSD raised nothing and
        # did nothing.
        direction: Union[int, str] = scroll_direction
        if is_windows() or is_macos():
            mouse.scroll(scroll_value)
        elif is_x11_unix():
            # Windows 與 macOS 只有一條滾輪軸，那兩個平台的表是 None。
            # Windows and macOS have a single wheel axis and publish no table.
            if special_mouse_keys_table is not None:
                direction = special_mouse_keys_table.get(scroll_direction, scroll_direction)
            mouse.scroll(scroll_value, direction)
        else:
            raise AutoControlMouseException(
                f"mouse_scroll: no backend for {sys.platform!r}")

        record_action_to_list("mouse_scroll", param)
        return scroll_value, direction

    except AutoControlMouseException as error:
        autocontrol_logger.error(f"mouse_scroll failed: {repr(error)}")
        raise AutoControlMouseException(mouse_scroll_error_message + " " + repr(error)) from error


def send_mouse_event_to_window(window: Union[int, str],
                               mouse_keycode: Union[int, str],
                               x: Optional[int] = None,
                               y: Optional[int] = None) -> None:
    """
    將滑鼠事件送到指定視窗（**已棄用**，改用 ``post_click_to_window``）
    Send mouse event to a specific window. **Deprecated** — use
    ``je_auto_control.post_click_to_window``.

    原本把訊息投遞給傳進來的那個 handle，也就是**頂層視窗**；但點擊要送給座標
    底下的**子控制項**、而且座標要換算成那個控制項的 client 座標，否則點不到
    任何東西。這支現在轉呼叫修好的路徑：`window` 傳字串就當**標題片段**（與其餘
    視窗函式一致），傳整數仍當 hwnd（維持舊呼叫端的型別）。

    Posted to whatever handle it was given — the top-level frame — but a click
    belongs to the child control under the point, in that control's client
    coordinates. It now delegates to the fixed path: a string ``window`` is a
    title substring (consistent with every other window function), an int is
    still an hwnd.

    :param window: 視窗 handle 或標題片段 Window handle or title substring
    :param mouse_keycode: 滑鼠按鍵代碼 Mouse keycode
    :param x: X 座標（相對視窗左上角）X position, relative to the window
    :param y: Y 座標 Y position
    """
    warnings.warn(
        "send_mouse_event_to_window is deprecated; use post_click_to_window. "
        "The old implementation posted to the top-level frame, so the click "
        "landed on nothing in any window with child controls.",
        DeprecationWarning, stacklevel=2,
    )
    autocontrol_logger.info(f"send_mouse_event_to_window, window={window}, keycode={mouse_keycode}, x={x}, y={y}")
    param = {"window": window, "keycode": mouse_keycode, "x": x, "y": y}
    if sys.platform == "darwin":
        autocontrol_logger.warning("send_mouse_event_to_window not supported on macOS")
        return
    try:
        button = _button_name_for_post(mouse_keycode)
        if isinstance(window, str):
            from je_auto_control.wrapper.auto_control_window import (
                post_click_to_window,
            )
            posted = post_click_to_window(window, button, int(x or 0), int(y or 0))
        else:
            from je_auto_control.windows.window import windows_window_manage as wm
            posted = wm.post_click(int(window), button, int(x or 0), int(y or 0))
        record_action_to_list("send_mouse_event_to_window", {**param, "posted": posted})

    except Exception as error:  # noqa: BLE001 - preserved contract: never raises
        record_action_to_list("send_mouse_event_to_window", param, repr(error))
        autocontrol_logger.error(f"send_mouse_event_to_window failed: {repr(error)}")


def _button_name_for_post(mouse_keycode: Union[int, str]) -> str:
    """把舊介面收的按鍵代碼轉成投遞路徑用的按鍵名。

    舊介面同時吃名稱（``mouse_left``）與底層代碼元組；後者反查回名稱，查不到就
    當左鍵並記一筆——這條是相容路徑，不值得為了它讓呼叫端爆掉。
    """
    if isinstance(mouse_keycode, str):
        name = mouse_keycode.lower()
        return name[len("mouse_"):] if name.startswith("mouse_") else name
    for name, code in mouse_keys_table.items():
        if code == mouse_keycode:
            return name[len("mouse_"):]
    autocontrol_logger.warning(
        "send_mouse_event_to_window: unknown keycode %r, assuming left",
        mouse_keycode)
    return "left"
