"""Read the live IME (input method editor) state for safe CJK entry.

Typing into a CJK / Japanese / Korean field is unsafe while an IME is *composing*:
the candidate text has not been committed yet, so reading the field back returns
half-entered glyphs and the next keystroke edits the composition instead of the
field. ``text_unicode`` (``VK_PACKET``) is blind to this. ``ime_state`` exposes
the live composition and conversion state so a flow can wait for the IME to
commit before it reads or acts.

* :func:`ime_state` — ``{open, composing, composition, conversion}`` for the
  focused window's IME, through an injectable ``reader``.
* :func:`is_composing` — ``True`` while the IME has an uncommitted composition.
* :func:`wait_for_composition_commit` — block until composition ends (or a
  timeout), with injectable ``clock`` / ``sleep`` / ``reader``.
* :func:`decode_conversion_mode` — pure: the IMM32 ``IME_CMODE_*`` conversion
  bitmask to ``{native, katakana, full_shape, roman, char_code}``.

The default ``reader`` queries Windows IMM32 (``ImmGetContext`` /
``ImmGetOpenStatus`` / ``ImmGetConversionStatus`` / ``ImmGetCompositionStringW``)
read-only; all decoding / waiting logic runs through the injectable seam, so it
is fully testable without an IME. Imports no ``PySide6``.
"""
import sys
import time
from typing import Any, Callable, Dict, Optional

# IMM32 conversion-mode (IME_CMODE_*) bit flags.
IME_CMODE_NATIVE = 0x0001
IME_CMODE_KATAKANA = 0x0002
IME_CMODE_FULLSHAPE = 0x0008
IME_CMODE_ROMAN = 0x0010
IME_CMODE_CHARCODE = 0x0020

# A reader returns the raw IME state: {open, conversion, composition}.
ImeReader = Callable[[], Dict[str, Any]]


def decode_conversion_mode(flags: int) -> Dict[str, bool]:
    """Decode an IMM32 ``IME_CMODE_*`` bitmask into named booleans (pure)."""
    value = int(flags)
    return {
        "native": bool(value & IME_CMODE_NATIVE),
        "katakana": bool(value & IME_CMODE_KATAKANA),
        "full_shape": bool(value & IME_CMODE_FULLSHAPE),
        "roman": bool(value & IME_CMODE_ROMAN),
        "char_code": bool(value & IME_CMODE_CHARCODE),
    }


def _normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Turn a raw reader result into the public IME-state dict (pure)."""
    composition = str(raw.get("composition") or "")
    flags = int(raw.get("conversion") or 0)
    return {
        "open": bool(raw.get("open")),
        "composing": bool(composition),
        "composition": composition,
        "conversion": decode_conversion_mode(flags),
        "conversion_flags": flags,
    }


def ime_state(*, reader: Optional[ImeReader] = None) -> Dict[str, Any]:
    """Return the focused window's IME state.

    ``{open, composing, composition, conversion, conversion_flags}``. Pass
    ``reader`` (a ``() -> {open, conversion, composition}``) to supply the
    reading in tests; the default queries Windows IMM32.
    """
    source = reader if reader is not None else _default_reader
    return _normalize(source())


def is_composing(*, reader: Optional[ImeReader] = None) -> bool:
    """Return ``True`` while the IME has an uncommitted composition."""
    return bool(ime_state(reader=reader)["composing"])


def wait_for_composition_commit(
        *, reader: Optional[ImeReader] = None, timeout_s: float = 5.0,
        interval_s: float = 0.1, clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep) -> bool:
    """Block until the IME is no longer composing; ``True``, or ``False`` on timeout.

    ``clock`` / ``sleep`` / ``reader`` are injectable for deterministic tests.
    """
    deadline = clock() + float(timeout_s)
    while True:
        if not is_composing(reader=reader):
            return True
        if clock() >= deadline:
            return False
        sleep(float(interval_s))


# IMM32 composition-string flag: read the in-progress composition (GCS_COMPSTR).
_GCS_COMPSTR = 0x0008


def _read_composition(imm32: Any, himc: int) -> str:
    """Read the in-progress composition string from an IME context."""
    import ctypes
    byte_len = imm32.ImmGetCompositionStringW(himc, _GCS_COMPSTR, None, 0)
    if byte_len <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(byte_len // 2)
    imm32.ImmGetCompositionStringW(himc, _GCS_COMPSTR, buffer, byte_len)
    return buffer.value


def _default_reader() -> Dict[str, Any]:
    """Read the focused window's IME state from Windows IMM32 (read-only)."""
    if not sys.platform.startswith("win"):
        raise RuntimeError(
            "IME state has no OS reader on this platform; pass reader=")
    import ctypes
    user32 = ctypes.windll.user32
    imm32 = ctypes.windll.imm32
    hwnd = user32.GetForegroundWindow()
    himc = imm32.ImmGetContext(hwnd)
    if not himc:
        return {"open": False, "conversion": 0, "composition": ""}
    try:
        conversion = ctypes.c_uint(0)
        sentence = ctypes.c_uint(0)
        imm32.ImmGetConversionStatus(
            himc, ctypes.byref(conversion), ctypes.byref(sentence))
        return {
            "open": bool(imm32.ImmGetOpenStatus(himc)),
            "conversion": int(conversion.value),
            "composition": _read_composition(imm32, himc),
        }
    finally:
        imm32.ImmReleaseContext(hwnd, himc)
