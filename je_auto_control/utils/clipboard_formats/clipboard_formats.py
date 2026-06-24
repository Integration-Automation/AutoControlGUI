"""Inspect and classify the clipboard's available formats.

The clipboard usually holds the *same* content in several formats at once — a
copy from Word offers ``CF_UNICODETEXT`` + ``HTML Format`` + ``Rich Text Format``,
a file copy offers ``CF_HDROP``, a screenshot offers ``CF_DIB``. Knowing *which
formats are present* (without consuming any of them) tells an automation what it
can paste and lets it detect when the clipboard's shape changed.

``clipboard_formats`` enumerates the live clipboard (``EnumClipboardFormats``) and
classifies each format into a friendly category (text / image / files / html /
rtf / csv / audio / …). The classifier and the snapshot diff are pure functions —
unit-testable on any platform — and only the live enumeration is Win32 (raising
``RuntimeError`` elsewhere, like the base ``clipboard`` module). Imports no
``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# Standard CF_* clipboard format ids → category.
_CF_CATEGORY = {
    1: "text", 7: "text", 13: "text",            # CF_TEXT / OEMTEXT / UNICODETEXT
    2: "image", 8: "image", 17: "image",          # CF_BITMAP / DIB / DIBV5
    3: "image", 6: "image", 14: "image",          # METAFILEPICT / TIFF / ENHMETAFILE
    9: "palette",                                  # CF_PALETTE
    11: "audio", 12: "audio",                      # CF_RIFF / CF_WAVE
    15: "files",                                   # CF_HDROP
    16: "locale",                                  # CF_LOCALE
}
# Registered (named) clipboard formats → category (matched case-insensitively).
_NAME_CATEGORY = {
    "html format": "html",
    "rich text format": "rtf",
    "rich text format without objects": "rtf",
    "csv": "csv",
    "png": "image", "jfif": "image", "gif": "image", "image/png": "image",
    "filenamew": "files", "filename": "files", "filegroupdescriptorw": "files",
    "filegroupdescriptor": "files", "shell idlist array": "files",
}
_Format = Union[int, Dict[str, Any], Tuple[int, str]]


def _coerce(item: _Format) -> Tuple[int, str]:
    """Normalise a format descriptor (int / ``{id,name}`` / ``(id,name)``)."""
    if isinstance(item, dict):
        return int(item.get("id", 0)), str(item.get("name") or "")
    if isinstance(item, (tuple, list)):
        return int(item[0]), str(item[1] if len(item) > 1 else "")
    return int(item), ""


def classify_format(format_id: int, name: Optional[str] = None) -> str:
    """Return the friendly category for one clipboard format.

    A registered ``name`` (e.g. ``"HTML Format"``) takes priority; otherwise the
    standard ``CF_*`` id is mapped. Anything unrecognised is ``"other"``.
    """
    if name:
        category = _NAME_CATEGORY.get(name.strip().lower())
        if category is not None:
            return category
    return _CF_CATEGORY.get(int(format_id), "other")


def classify_formats(formats: Sequence[_Format]) -> Dict[str, Any]:
    """Classify a list of clipboard formats into a summary.

    Returns ``{categories, formats:[{id,name,category}], has_text, has_image,
    has_files}``.
    """
    items: List[Dict[str, Any]] = []
    for entry in formats:
        format_id, name = _coerce(entry)
        items.append({"id": format_id, "name": name,
                      "category": classify_format(format_id, name)})
    categories = sorted({item["category"] for item in items})
    return {"categories": categories, "formats": items,
            "has_text": "text" in categories,
            "has_image": "image" in categories,
            "has_files": "files" in categories}


def diff_formats(before: Sequence[_Format],
                 after: Sequence[_Format]) -> Dict[str, Any]:
    """Diff two clipboard-format snapshots into ``{added, removed, changed}``.

    ``added`` / ``removed`` are classified format dicts; ``changed`` is True when
    either is non-empty — a pure monitor primitive over two enumerations.
    """
    def keyed(formats: Sequence[_Format]) -> Dict[Tuple[int, str], Dict[str, Any]]:
        out: Dict[Tuple[int, str], Dict[str, Any]] = {}
        for entry in formats:
            format_id, name = _coerce(entry)
            out[(format_id, name)] = {"id": format_id, "name": name,
                                      "category": classify_format(format_id, name)}
        return out

    before_map, after_map = keyed(before), keyed(after)
    added = [after_map[k] for k in after_map if k not in before_map]
    removed = [before_map[k] for k in before_map if k not in after_map]
    return {"added": added, "removed": removed,
            "changed": bool(added or removed)}


# --- Win32 live enumeration ------------------------------------------------

def _format_name(user32, format_id: int) -> str:
    import ctypes
    buffer = ctypes.create_unicode_buffer(256)
    if user32.GetClipboardFormatNameW(format_id, buffer, 256):
        return buffer.value
    return ""


def list_clipboard_formats() -> List[Dict[str, Any]]:
    """Return the formats currently on the clipboard as ``[{id, name}]`` (Windows)."""
    import sys
    if not sys.platform.startswith("win"):
        raise RuntimeError("list_clipboard_formats is only supported on Windows")
    import ctypes
    user32 = ctypes.windll.user32
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        formats: List[Dict[str, Any]] = []
        format_id = user32.EnumClipboardFormats(0)
        while format_id:
            formats.append({"id": int(format_id),
                            "name": _format_name(user32, format_id)})
            format_id = user32.EnumClipboardFormats(format_id)
        return formats
    finally:
        user32.CloseClipboard()


def clipboard_formats() -> Dict[str, Any]:
    """Enumerate and classify the live clipboard's formats (Windows).

    Returns the :func:`classify_formats` summary for whatever is on the
    clipboard right now, without consuming any format.
    """
    return classify_formats(list_clipboard_formats())
