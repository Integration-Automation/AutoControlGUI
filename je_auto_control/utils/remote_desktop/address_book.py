"""Persistent viewer-side address book of saved hosts.

Mirrors AnyDesk's "recents + favorites" panel: each entry stores the
signaling server URL, host_id, an optional friendly label, and a
``last_used`` timestamp so the GUI can sort by recency.

Storage: ``~/.je_auto_control/address_book.json``::

    {
        "entries": [
            {"label": "home desktop", "server_url": "http://...",
             "host_id": "abc12345", "last_used": "2025-04-27T..."}
        ]
    }
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_PATH_RELATIVE = ".je_auto_control/address_book.json"


def default_address_book_path() -> Path:
    home = Path(os.path.expanduser("~"))
    return home / _DEFAULT_PATH_RELATIVE


class AddressBook:
    """Thread-safe JSON-backed list of host endpoints."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = (Path(path) if path is not None
                      else default_address_book_path())
        self._lock = threading.Lock()
        self._entries: List[dict] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            autocontrol_logger.warning("address book load failed: %r", error)
            return
        if isinstance(data, dict):
            entries = data.get("entries", [])
            self._entries = [e for e in entries if isinstance(e, dict)
                             and isinstance(e.get("host_id"), str)]

    def _save(self) -> None:
        payload = {"entries": self._entries}
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
            autocontrol_logger.warning("address book save failed: %r", error)

    # --- public API ---------------------------------------------------------

    def list_entries(self) -> List[dict]:
        with self._lock:
            return [dict(entry) for entry in self._entries]

    def upsert(self, *, host_id: str, server_url: str,
               label: str = "", mac_address: Optional[str] = None,
               broadcast_address: Optional[str] = None) -> None:
        """Insert or refresh an entry; updates ``last_used`` to now."""
        if not host_id or not server_url:
            raise ValueError("host_id and server_url are required")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._find_entry_locked(host_id, server_url)
            if existing is not None:
                self._refresh_entry_locked(
                    existing, now=now, label=label,
                    mac_address=mac_address,
                    broadcast_address=broadcast_address,
                )
            else:
                self._entries.append(self._build_entry(
                    host_id=host_id, server_url=server_url,
                    label=label, now=now,
                    mac_address=mac_address,
                    broadcast_address=broadcast_address,
                ))
            self._save()

    def _find_entry_locked(self, host_id: str,
                           server_url: str) -> Optional[dict]:
        for entry in self._entries:
            if (entry.get("host_id") == host_id
                    and entry.get("server_url") == server_url):
                return entry
        return None

    @staticmethod
    def _refresh_entry_locked(entry: dict, *, now: str, label: str,
                              mac_address: Optional[str],
                              broadcast_address: Optional[str]) -> None:
        entry["last_used"] = now
        if label:
            entry["label"] = label
        if mac_address is not None:
            entry["mac_address"] = mac_address
        if broadcast_address is not None:
            entry["broadcast_address"] = broadcast_address
        entry.setdefault("favorite", False)

    @staticmethod
    def _build_entry(*, host_id: str, server_url: str,
                     label: str, now: str,
                     mac_address: Optional[str],
                     broadcast_address: Optional[str]) -> dict:
        new_entry = {
            "label": label,
            "server_url": server_url,
            "host_id": host_id,
            "last_used": now,
            "favorite": False,
        }
        if mac_address:
            new_entry["mac_address"] = mac_address
        if broadcast_address:
            new_entry["broadcast_address"] = broadcast_address
        return new_entry

    def set_tags(self, *, host_id: str, server_url: str,
                 tags: list) -> None:
        """Replace ``tags`` on the matching entry."""
        clean = [str(t).strip() for t in tags if str(t).strip()]
        with self._lock:
            for entry in self._entries:
                if (entry.get("host_id") == host_id
                        and entry.get("server_url") == server_url):
                    entry["tags"] = clean
                    self._save()
                    return

    def all_tags(self) -> list:
        """Return distinct tags across all entries (sorted)."""
        seen = set()
        with self._lock:
            for entry in self._entries:
                for t in entry.get("tags", []) or []:
                    if isinstance(t, str) and t.strip():
                        seen.add(t.strip())
        return sorted(seen)

    def toggle_favorite(self, *, host_id: str, server_url: str) -> bool:
        """Flip ``favorite`` on the matching entry; returns the new state."""
        with self._lock:
            for entry in self._entries:
                if (entry.get("host_id") == host_id
                        and entry.get("server_url") == server_url):
                    new_state = not entry.get("favorite", False)
                    entry["favorite"] = new_state
                    self._save()
                    return new_state
        return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._save()

    def remove(self, *, host_id: str, server_url: str) -> bool:
        with self._lock:
            before = len(self._entries)
            self._entries = [
                e for e in self._entries
                if not (e.get("host_id") == host_id
                        and e.get("server_url") == server_url)
            ]
            removed = len(self._entries) < before
            if removed:
                self._save()
        return removed


_default_address_book: Optional[AddressBook] = None
_default_lock = threading.Lock()


def default_address_book() -> AddressBook:
    """Return a process-wide AddressBook using the default on-disk path."""
    global _default_address_book
    with _default_lock:
        if _default_address_book is None:
            _default_address_book = AddressBook()
        return _default_address_book


__all__ = ["AddressBook", "default_address_book", "default_address_book_path"]
