"""Key names that mean a character, resolved through the keyboard layout.

``oem_2`` is the ``/`` key on a US keyboard and something else elsewhere, so a
readable alias that pointed at a fixed ``oem_N`` would lie on most layouts --
which is why the Windows key table had none. The names here are different:
``slash`` means "the key that types ``/``", and the virtual key is looked up
when the name is, with ``VkKeyScanExW`` on the character against the layout
of the foreground window (where the key press is going).

A layout that has no bare key for the character -- German types ``/`` with
Shift+7 -- gives the key at the US position, which is also what an unknown
layout, a failed probe and a non-Windows import give. The table therefore
always holds a valid virtual key for every name, and iterating it (the key
list in the GUI, ``AC_get_keyboard_keys_table``) shows those US positions.

Nothing here sends input, and the module imports no Windows API until a
lookup needs one, so it can be imported -- and tested with a fake ``user32``
-- on any platform.
"""
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from je_auto_control.utils.keyboard_layout.keyboard_layout import (
    foreground_keyboard_layout,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

#: alias -> (the character the key types, its key name on a US keyboard).
LAYOUT_KEY_ALIASES: Dict[str, Tuple[str, str]] = {
    "slash": ("/", "oem_2"),
    "backslash": ("\\", "oem_5"),
    "semicolon": (";", "oem_1"),
    "quote": ("'", "oem_7"),
    "backquote": ("`", "oem_3"),
    "bracketleft": ("[", "oem_4"),
    "bracketright": ("]", "oem_6"),
    "equal": ("=", "oem_plus"),
}

#: ``VkKeyScanExW`` answers -1 when no key of the layout types the character.
_NO_KEY = -1


def _user32() -> Any:
    """A private ``user32`` handle, so the prototype set below is ours alone."""
    import ctypes
    # getattr: the name exists on Windows only, which is where this is called.
    return getattr(ctypes, "WinDLL")("user32")


def layout_virtual_key(character: str) -> Optional[int]:
    """The key that types ``character`` unmodified on the active layout.

    ``None`` when the layout cannot be probed, has no key for the character,
    or types it only with Shift, Ctrl or AltGr held -- the caller then uses
    the US position.
    """
    layout = foreground_keyboard_layout()
    if layout is None:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = _user32()
        user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, wintypes.HKL]
        user32.VkKeyScanExW.restype = ctypes.c_short
        scanned = int(user32.VkKeyScanExW(character, layout))
    except (OSError, AttributeError, ValueError, TypeError) as error:
        autocontrol_logger.info("layout key lookup for %r failed: %r", character, error)
        return None
    if scanned == _NO_KEY:
        return None
    virtual_key, shift_state = scanned & 0xFF, (scanned >> 8) & 0xFF
    return virtual_key if shift_state == 0 and virtual_key else None


class LayoutKeyTable(Dict[str, int]):
    """A key table whose layout-dependent names are resolved at lookup time.

    A plain ``dict`` in every other respect: the layout names are stored with
    their US-position codes, so membership, iteration and length behave as
    before. Only ``table[name]`` and ``table.get(name)`` ask the layout.
    """

    def __init__(self, table: Mapping[str, int],
                 aliases: Optional[Mapping[str, Tuple[str, str]]] = None) -> None:
        super().__init__(table)
        self._characters: Dict[str, str] = {}
        for alias, (character, us_name) in (aliases or LAYOUT_KEY_ALIASES).items():
            if alias in self:
                continue    # an existing name keeps its code and stays static
            self._characters[alias] = character
            super().__setitem__(alias, super().__getitem__(us_name))

    def layout_names(self) -> Iterable[str]:
        """The names resolved through the layout."""
        return tuple(self._characters)

    def _resolved(self, name: Any) -> Optional[int]:
        character = self._characters.get(name) if isinstance(name, str) else None
        return layout_virtual_key(character) if character is not None else None

    def __getitem__(self, name: str) -> int:
        resolved = self._resolved(name)
        return resolved if resolved is not None else super().__getitem__(name)

    def get(self, name: str, default: Any = None) -> Any:
        """``dict.get``, asking the layout for the names that depend on it."""
        resolved = self._resolved(name)
        return resolved if resolved is not None else super().get(name, default)


__all__ = ["LAYOUT_KEY_ALIASES", "LayoutKeyTable", "layout_virtual_key"]
