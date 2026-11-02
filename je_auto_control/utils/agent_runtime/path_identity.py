"""Resolve a path for identity checks without mistaking Windows' extended-length spelling for a redirect."""
from __future__ import annotations

import os
from pathlib import Path

_EXTENDED = '\\\\?\\'
_EXTENDED_UNC = _EXTENDED + 'UNC\\'


def plain_spelling(text: str) -> str:
    """Drop a ``\\\\?\\`` prefix from a drive or UNC path; any other spelling is returned unchanged."""
    if text.startswith(_EXTENDED_UNC):
        return '\\\\' + text[len(_EXTENDED_UNC):]
    rest = text[len(_EXTENDED):]
    if text.startswith(_EXTENDED) and len(rest) > 2 and rest[0].isalpha() and rest[1:3] == ':\\':
        return rest
    return text


def resolved(path: Path) -> Path:
    """Return ``path.resolve()`` in the spelling of ``path``.

    ``ntpath.realpath`` keeps the ``\\\\?\\`` prefix when a path that was missing appears while it is
    being resolved and cannot be opened yet, as when another thread is creating that same directory.
    Both spellings name the same file, so an identity check comparing against ``path`` must not see
    the prefix as a different location.
    """
    value = path.resolve()
    if os.name != 'nt' or str(path).startswith(_EXTENDED):
        return value
    return Path(plain_spelling(str(value)))
