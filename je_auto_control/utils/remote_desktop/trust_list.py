"""Persistent trust list of viewer IDs that auto-accept on connect.

When a viewer authenticates with a viewer_id present in the trust list,
the host bypasses the accept/reject prompt — enabling AnyDesk-style
unattended access for known machines.

Storage: ``~/.je_auto_control/trusted_viewers.json``::

    {
        "viewers": [
            {"viewer_id": "abc...", "label": "office laptop",
             "added_at": "2025-04-27T10:30:00Z"}
        ]
    }
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_PATH_RELATIVE = ".je_auto_control/trusted_viewers.json"


def default_trust_list_path() -> Path:
    home = Path(os.path.expanduser("~"))
    return home / _DEFAULT_PATH_RELATIVE


class TrustList:
    """Thread-safe JSON-backed list of trusted viewer IDs."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_trust_list_path()
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        self._load()

    # --- persistence --------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            autocontrol_logger.warning("trust list load failed: %r", error)
            return
        if not isinstance(data, dict):
            return
        for entry in data.get("viewers", []):
            if not isinstance(entry, dict):
                continue
            viewer_id = entry.get("viewer_id")
            if isinstance(viewer_id, str) and viewer_id:
                self._entries[viewer_id] = entry

    def _save(self) -> None:
        payload = {"viewers": list(self._entries.values())}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass
        except OSError as error:
            autocontrol_logger.warning("trust list save failed: %r", error)

    # --- public API ---------------------------------------------------------

    def is_trusted(self, viewer_id: str) -> bool:
        if not isinstance(viewer_id, str):
            return False
        with self._lock:
            return viewer_id in self._entries

    def add(self, viewer_id: str, label: str = "") -> None:
        if not isinstance(viewer_id, str) or not viewer_id:
            raise ValueError("viewer_id must be a non-empty string")
        entry = {
            "viewer_id": viewer_id,
            "label": label,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "last_used": None,
        }
        with self._lock:
            existing = self._entries.get(viewer_id) or {}
            entry["last_used"] = existing.get("last_used")
            entry["added_at"] = existing.get("added_at", entry["added_at"])
            if not label and existing.get("label"):
                entry["label"] = existing["label"]
            self._entries[viewer_id] = entry
            self._save()

    def touch(self, viewer_id: str) -> None:
        """Update last_used to now for a previously trusted viewer."""
        with self._lock:
            entry = self._entries.get(viewer_id)
            if entry is None:
                return
            entry["last_used"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def remove(self, viewer_id: str) -> bool:
        with self._lock:
            removed = self._entries.pop(viewer_id, None) is not None
            if removed:
                self._save()
        return removed

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._save()

    def list_entries(self) -> List[dict]:
        with self._lock:
            return [dict(entry) for entry in self._entries.values()]


_default_trust_list: Optional[TrustList] = None
_default_lock = threading.Lock()


def default_trust_list() -> TrustList:
    """Return a process-wide TrustList using the default on-disk path."""
    global _default_trust_list
    with _default_lock:
        if _default_trust_list is None:
            _default_trust_list = TrustList()
        return _default_trust_list


__all__ = ["TrustList", "default_trust_list", "default_trust_list_path"]
