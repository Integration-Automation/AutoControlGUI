"""Read an on / off flag from an action argument by its spelling, not its truthiness.

A value from a JSON action file, a CLI argument, the socket server or an MCP
call can arrive as the string ``"false"``, which ``bool()`` reads as true:
``"ignore_case": "false"`` turned case folding on, and ``"paste": "false"``
pasted, overwriting the user's clipboard. Every adapter and flow command reads
its flags through :func:`as_bool`. Imports no ``PySide6``.
"""
from typing import Any

#: String spellings of an "on" flag; any other string is "off".
_TRUE_SPELLINGS = ("1", "true", "yes", "on")


def as_bool(value: Any) -> bool:
    """``value`` as a flag: a string by its spelling (``"true"`` / ``"yes"`` / ``"on"`` / ``"1"``), else ``bool()``."""
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_SPELLINGS
    return bool(value)
