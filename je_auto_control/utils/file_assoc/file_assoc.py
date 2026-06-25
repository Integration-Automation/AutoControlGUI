"""Resolve which application is registered to open a given file type.

:func:`shell_open` opens a file with whatever app is registered for it;
``file_assoc`` answers the inverse, read-only question — *which* app is that?
Given ``report.pdf`` (or a bare ``.pdf`` / ``pdf``) it returns the registered
executable, the friendly app name, the open command line and the MIME content
type, via the Windows ``AssocQueryStringW`` shell API.

:func:`normalize_ext` is a pure helper (path / bare-extension -> ``.ext``),
fully unit-testable. :func:`file_association` runs the lookup through an
injectable ``resolver`` seam (the real shell API by default), so the assembly
logic is testable without Windows. Imports no ``PySide6``.
"""
import ctypes
import os
import sys
from typing import Any, Callable, Dict, Optional

# ASSOCSTR query ids (shlwapi AssocQueryStringW) -> result-dict keys.
_ASSOC_FIELDS = {
    "command": 1,        # ASSOCSTR_COMMAND
    "exe": 2,            # ASSOCSTR_EXECUTABLE
    "friendly": 4,       # ASSOCSTR_FRIENDLYAPPNAME
    "content_type": 12,  # ASSOCSTR_CONTENTTYPE
}

# A resolver: ext (".pdf") -> {command, exe, friendly, content_type}.
AssocResolver = Callable[[str], Dict[str, Any]]


def normalize_ext(target: str) -> str:
    """Return the lowercased extension (with leading dot) of a path or ext.

    Accepts ``report.pdf``, ``C:\\x\\y.PDF``, ``.pdf`` or bare ``pdf``. Raises
    ``ValueError`` for an empty target or one with no resolvable extension.
    """
    text = str(target).strip()
    if not text:
        raise ValueError("target is empty")
    _, ext = os.path.splitext(os.path.basename(text))
    if not ext:
        ext = text if text.startswith(".") else "." + text
    ext = ext.lower()
    if len(ext) < 2 or any(char in ext for char in "/\\ \t"):
        raise ValueError(f"no file extension in target: {target!r}")
    return ext


def _assoc_query(ext: str, assoc_str: int) -> Optional[str]:
    """Run one AssocQueryStringW lookup; return the string or None."""
    shlwapi = ctypes.windll.shlwapi
    size = ctypes.c_ulong(0)
    shlwapi.AssocQueryStringW(0, assoc_str, ext, None, None, ctypes.byref(size))
    if size.value == 0:
        return None
    buf = ctypes.create_unicode_buffer(size.value)
    result = shlwapi.AssocQueryStringW(0, assoc_str, ext, None, buf,
                                       ctypes.byref(size))
    return buf.value if result == 0 else None


def _default_resolver(ext: str) -> Dict[str, Any]:
    """Resolve ``ext``'s registered app via the Windows shell API."""
    if not sys.platform.startswith("win"):
        raise RuntimeError(
            "file association lookup is Windows-only; pass resolver=")
    return {key: _assoc_query(ext, assoc_str)
            for key, assoc_str in _ASSOC_FIELDS.items()}


def file_association(target: str, *,
                     resolver: Optional[AssocResolver] = None) -> Dict[str, Any]:
    """Return the app registered to open ``target``'s file type.

    Returns ``{ext, command, exe, friendly, content_type}`` (the app fields are
    None when nothing is registered). Pass ``resolver`` (``ext -> dict``) to
    intercept the lookup in tests; the default uses the Windows shell API.
    """
    ext = normalize_ext(target)
    resolve = resolver if resolver is not None else _default_resolver
    info = resolve(ext)
    return {"ext": ext,
            "command": info.get("command"),
            "exe": info.get("exe"),
            "friendly": info.get("friendly"),
            "content_type": info.get("content_type")}
