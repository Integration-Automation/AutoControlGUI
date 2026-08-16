"""Ask the system what character each key produces on the active layout.

A recorded session stores *virtual key codes*, but a replay — and anything that
shows the user what was recorded — needs characters. The mapping is not fixed:
letters and digits agree across Latin layouts, punctuation does not, so a
hard-coded US table mislabels every punctuation key on a German, French or
Nordic keyboard.

Two pieces of timing make this correct rather than nearly correct:

* **Ask about the foreground window's layout, not this thread's.** The user is
  typing into whatever is in front; this process's own thread can be on a
  completely different layout.
* **Translate after recording, never during.** ``ToUnicodeEx`` mutates the
  keyboard's dead-key composition state, so calling it while someone is typing
  corrupts the character they are half-way through composing. Record key codes,
  translate once at the end, then flush the state.

Falls back to the US table where the OS cannot answer, and returns an empty
mapping off Windows. Imports no ``PySide6``.
"""
import sys
from typing import Dict, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# Virtual key code -> (unshifted, shifted) on a **US** layout. Only the fallback
# for when the OS will not answer; letters and digits are layout-independent
# anyway, punctuation is what actually differs.
US_PRINTABLE_VK: Dict[int, Tuple[str, str]] = {
    **{vk: (chr(vk).lower(), chr(vk)) for vk in range(0x41, 0x5B)},      # A-Z
    **{vk: (chr(vk), shifted) for vk, shifted
       in zip(range(0x30, 0x3A), ")!@#$%^&*(")},                        # 0-9
    **{vk: (chr(0x30 + vk - 0x60),) * 2 for vk in range(0x60, 0x6A)},   # numpad
    0x20: (" ", " "),
    0xBA: (";", ":"), 0xBB: ("=", "+"), 0xBC: (",", "<"), 0xBD: ("-", "_"),
    0xBE: (".", ">"), 0xBF: ("/", "?"), 0xC0: ("`", "~"),
    0xDB: ("[", "{"), 0xDC: ("\\", "|"), 0xDD: ("]", "}"), 0xDE: ("'", '"'),
    0x6A: ("*", "*"), 0x6B: ("+", "+"), 0x6D: ("-", "-"),
    0x6E: (".", "."), 0x6F: ("/", "/"),
}

_VK_SHIFT = 0x10
_VK_SPACE = 0x20
_MAPVK_VK_TO_VSC = 0
_LAYOUT_CACHE: Dict[int, Dict[int, Tuple[str, str]]] = {}


def foreground_keyboard_layout() -> Optional[int]:
    """The layout handle the **foreground** window's thread is using."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        window = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(window, None) if window else 0
        return int(user32.GetKeyboardLayout(thread_id))
    except (OSError, AttributeError, ValueError) as error:
        autocontrol_logger.info("keyboard layout probe failed: %r", error)
        return None


def _translator(user32, layout: int):
    """Return ``translate(vk, shifted) -> str`` for one layout."""
    import ctypes
    from ctypes import wintypes
    user32.ToUnicodeEx.argtypes = [
        wintypes.UINT, wintypes.UINT, ctypes.c_char * 256, wintypes.LPWSTR,
        ctypes.c_int, wintypes.UINT, wintypes.HKL]
    user32.ToUnicodeEx.restype = ctypes.c_int
    user32.MapVirtualKeyExW.argtypes = [
        wintypes.UINT, wintypes.UINT, wintypes.HKL]
    user32.MapVirtualKeyExW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(8)

    def _translate(vk: int, shifted: bool) -> str:
        state = (ctypes.c_char * 256)()
        if shifted:
            state[_VK_SHIFT] = b"\x80"
        scan = user32.MapVirtualKeyExW(vk, _MAPVK_VK_TO_VSC, layout)
        count = user32.ToUnicodeEx(vk, scan, state, buffer, 8, 0, layout)
        if count == -1:
            # A dead key. Call again to clear it out of the composition buffer,
            # then report it as untranslatable rather than as its accent.
            user32.ToUnicodeEx(vk, scan, state, buffer, 8, 0, layout)
            return ""
        return buffer.value[:count] if count > 0 else ""

    return _translate


def _build_table(translate) -> Dict[int, Tuple[str, str]]:
    """Translate every candidate key, keeping only the printable results."""
    table: Dict[int, Tuple[str, str]] = {}
    for vk in US_PRINTABLE_VK:
        plain, shifted = translate(vk, False), translate(vk, True)
        if len(plain) == 1 and plain.isprintable():
            usable = len(shifted) == 1 and shifted.isprintable()
            table[vk] = (plain, shifted if usable else plain)
    translate(_VK_SPACE, False)          # flush any dead-key state left behind
    return table


def layout_char_table(layout: Optional[int] = None
                      ) -> Dict[int, Tuple[str, str]]:
    """``{vk: (unshifted, shifted)}`` for ``layout`` (default: the foreground one).

    Empty off Windows or when the OS will not answer, so callers can fall back
    to :data:`US_PRINTABLE_VK`.
    """
    if layout is None:
        layout = foreground_keyboard_layout()
    if layout is None or not sys.platform.startswith("win"):
        return {}
    if layout in _LAYOUT_CACHE:
        return _LAYOUT_CACHE[layout]
    try:
        import ctypes
        table = _build_table(_translator(ctypes.windll.user32, layout))
    except (OSError, AttributeError, ValueError) as error:
        autocontrol_logger.info("layout table build failed: %r", error)
        return {}
    _LAYOUT_CACHE[layout] = table
    return table


def char_table(layout: Optional[int] = None) -> Dict[int, Tuple[str, str]]:
    """The layout's table over the US fallback, so every known key is covered."""
    return {**US_PRINTABLE_VK, **layout_char_table(layout)}


def vk_to_char(vk: int, shifted: bool = False,
               table: Optional[Dict[int, Tuple[str, str]]] = None
               ) -> Optional[str]:
    """The character this key produces, or ``None`` if it produces none."""
    pair = (char_table() if table is None else table).get(int(vk))
    if pair is None:
        return None
    return pair[1] if shifted else pair[0]
