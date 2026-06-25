"""Read the live IME composition / conversion state for safe CJK entry."""
from je_auto_control.utils.ime_state.ime_state import (
    decode_conversion_mode, ime_state, is_composing,
    wait_for_composition_commit,
)

__all__ = [
    "ime_state", "is_composing", "wait_for_composition_commit",
    "decode_conversion_mode",
]
