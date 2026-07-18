"""Read/write a JSON object to a file, tolerating a missing/corrupt file.

Several stores (asset store, approval gate, …) persist a single JSON dict to
disk with identical boilerplate; this centralises it so they don't duplicate the
load/flush logic. Pure standard library; imports no ``PySide6``.
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union


def atomic_write_text(path: Union[str, Path], text: str,
                      encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` via a sibling temp file + rename.

    The new bytes land in a temp file in the same directory and only replace
    the destination once fully written, so a crash mid-write leaves the
    previous file intact instead of truncating it. Leftover temp files are
    removed on failure.
    """
    file_path = Path(path)
    directory = str(file_path.parent) or "."
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=f".{file_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding=encoding) as handle:
            handle.write(text)
        os.replace(tmp_name, str(file_path))
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def read_json_dict(path: Optional[Union[str, Path]]) -> Dict[str, Any]:
    """Return the JSON object at ``path``, or ``{}`` if missing/unreadable."""
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json_dict(path: Union[str, Path], data: Dict[str, Any]) -> None:
    """Write ``data`` as indented JSON to ``path`` (creating parent dirs)."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        file_path, json.dumps(data, ensure_ascii=False, indent=2))
