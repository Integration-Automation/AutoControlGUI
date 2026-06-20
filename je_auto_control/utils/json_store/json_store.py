"""Read/write a JSON object to a file, tolerating a missing/corrupt file.

Several stores (asset store, approval gate, …) persist a single JSON dict to
disk with identical boilerplate; this centralises it so they don't duplicate the
load/flush logic. Pure standard library; imports no ``PySide6``.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union


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
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
