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
from typing import Any, Callable, Dict, Optional, Tuple

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
#: Keys the US table has no row for but other layouts print from: ABNT C1/C2
#: (Brazilian), OEM_8 (UK and others), OEM_AX, and OEM_102 -- the extra key
#: beside left Shift on ISO boards (``<`` on German, French and Nordic ones).
#: Without them those keys never had a label on any layout.
_EXTRA_CANDIDATE_VK: Tuple[int, ...] = (0xC1, 0xC2, 0xDF, 0xE1, 0xE2)

#: ``{vk: (unshifted, shifted)}``; the shifted half is ``None`` for a key whose
#: Shift level prints no single character (a dead key, typically).
CharTable = Dict[int, Tuple[str, Optional[str]]]
_LAYOUT_CACHE: Dict[int, CharTable] = {}


def _user32() -> Any:
    """A ``user32`` handle of this module's own.

    ``ctypes.windll.user32`` is one object for the whole process, so a
    prototype set on it is set for everybody: after ``ToUnicodeEx.argtypes``
    was declared there with a ``c_char`` array, another caller passing the
    usual ``c_ubyte`` array got ``ArgumentError``. A separate ``WinDLL``
    carries its own prototypes.
    """
    import ctypes
    # getattr: the name exists on Windows only, which is where this is called.
    return getattr(ctypes, "WinDLL")("user32")


def foreground_keyboard_layout() -> Optional[int]:
    """The layout handle the **foreground** window's thread is using."""
    if not sys.platform.startswith("win"):
        return None
    try:
        user32 = _user32()
        window = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(window, None) if window else 0
        return int(user32.GetKeyboardLayout(thread_id))
    except (OSError, AttributeError, ValueError) as error:
        autocontrol_logger.info("keyboard layout probe failed: %r", error)
        return None


def _translator(user32: Any, layout: int) -> Callable[[int, bool], str]:
    """Return ``translate(vk, shifted) -> str`` for one layout.

    ``user32`` must be a private handle (:func:`_user32`): the prototypes
    below are set on whatever is passed in.
    """
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


def _build_table(translate: Callable[[int, bool], str]) -> CharTable:
    """Translate every candidate key, keeping only the printable results.

    A key whose Shift level is a dead key (Shift+6 on US-International) or
    prints nothing gets ``None`` for that half. It used to repeat the
    unshifted character, so Shift+6 was labelled ``6``.
    """
    table: CharTable = {}
    for vk in (*US_PRINTABLE_VK, *_EXTRA_CANDIDATE_VK):
        plain, shifted = translate(vk, False), translate(vk, True)
        if len(plain) == 1 and plain.isprintable():
            usable = len(shifted) == 1 and shifted.isprintable()
            table[vk] = (plain, shifted if usable else None)
    translate(_VK_SPACE, False)          # flush any dead-key state left behind
    return table


def layout_char_table(layout: Optional[int] = None) -> CharTable:
    """``{vk: (unshifted, shifted)}`` for ``layout`` (default: the foreground one).

    ``shifted`` is ``None`` where Shift plus the key prints no character.
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
        table = _build_table(_translator(_user32(), layout))
    except (OSError, AttributeError, ValueError) as error:
        autocontrol_logger.info("layout table build failed: %r", error)
        return {}
    _LAYOUT_CACHE[layout] = table
    return table


def char_table(layout: Optional[int] = None) -> CharTable:
    """The layout's table, or the US table when the layout cannot be read.

    Not merged: a key missing from the layout's table (a dead key such as
    the German ``^``) would otherwise get its US character.
    """
    return layout_char_table(layout) or dict(US_PRINTABLE_VK)


def vk_to_char(vk: int, shifted: bool = False,
               table: Optional[CharTable] = None
               ) -> Optional[str]:
    """The character this key produces, or ``None`` if it produces none."""
    pair = (char_table() if table is None else table).get(int(vk))
    if pair is None:
        return None
    return pair[1] if shifted else pair[0]
