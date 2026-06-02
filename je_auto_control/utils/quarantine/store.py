"""Quarantine store — close the loop on flaky tests.

:func:`analyze_flakiness` only *reports* unstable scripts. The quarantine
store *acts* on that report: a quarantined case name is skipped by the
:mod:`je_auto_control.utils.test_suite` runner (recorded as ``skipped``
with reason ``quarantined``) so a known-flaky case stops poisoning the
suite's red/green status until it is fixed and released.

The store is a small JSON file (mode 0600 on POSIX) that persists across
restarts, mirroring the other per-user config stores in the project.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


@dataclass
class QuarantineEntry:
    """One quarantined case name plus why and when."""

    name: str
    reason: str = ""
    added_at: float = 0.0
    flip_rate: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _default_path() -> Path:
    return Path.home() / ".je_auto_control" / "quarantine.json"


class QuarantineStore:
    """Thread-safe JSON-backed set of quarantined case names."""

    def __init__(self, path: Union[str, Path, None] = None) -> None:
        self._path = Path(path) if path is not None else _default_path()
        self._lock = threading.Lock()
        self._entries: Dict[str, QuarantineEntry] = {}
        self._load()

    @property
    def path(self) -> str:
        return str(self._path)

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            autocontrol_logger.warning("quarantine load failed: %r", error)
            return
        for item in raw.get("entries", []):
            name = item.get("name")
            if name:
                self._entries[name] = QuarantineEntry(
                    name=name, reason=item.get("reason", ""),
                    added_at=float(item.get("added_at", 0.0)),
                    flip_rate=item.get("flip_rate"),
                )

    def _save(self) -> None:
        payload = {"entries": [e.to_dict() for e in self._entries.values()]}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if os.name == "posix":
            try:
                os.chmod(self._path, 0o600)
            except OSError as error:
                autocontrol_logger.warning("quarantine chmod failed: %r", error)

    def add(self, name: str, reason: str = "",
            flip_rate: Optional[float] = None) -> QuarantineEntry:
        """Quarantine ``name`` (idempotent); return the stored entry."""
        if not name:
            raise ValueError("quarantine name must be non-empty")
        with self._lock:
            entry = QuarantineEntry(
                name=name, reason=reason, added_at=time.time(),
                flip_rate=flip_rate,
            )
            self._entries[name] = entry
            self._save()
        return entry

    def remove(self, name: str) -> bool:
        """Release ``name`` from quarantine; return False if absent."""
        with self._lock:
            if name not in self._entries:
                return False
            del self._entries[name]
            self._save()
        return True

    def is_quarantined(self, name: str) -> bool:
        return name in self._entries

    def names(self) -> Set[str]:
        return set(self._entries)

    def list(self) -> List[QuarantineEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name)

    def clear(self) -> int:
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._save()
        return count


_DEFAULT_STORE: Optional[QuarantineStore] = None


def default_quarantine_store() -> QuarantineStore:
    """Return the lazily-created shared quarantine store."""
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = QuarantineStore()
    return _DEFAULT_STORE


def quarantined_names() -> Set[str]:
    """Convenience: the set of quarantined names in the default store."""
    return default_quarantine_store().names()


def auto_quarantine_from_flakiness(flip_rate_threshold: float = 0.5,
                                   min_runs: int = 3,
                                   limit: int = 500,
                                   group_by: str = "script_path",
                                   store: Optional[QuarantineStore] = None,
                                   ) -> List[QuarantineEntry]:
    """Quarantine every flaky group whose flip rate meets the threshold.

    Reads the run-history flakiness report and adds qualifying entries to
    the quarantine store. Returns the entries added or refreshed.
    """
    from je_auto_control.utils.flakiness import analyze_flakiness
    target = store if store is not None else default_quarantine_store()
    report = analyze_flakiness(
        limit=int(limit), min_runs=int(min_runs), group_by=group_by,
    )
    added: List[QuarantineEntry] = []
    for entry in report.entries:
        if entry.flaky and entry.flip_rate >= flip_rate_threshold:
            added.append(target.add(
                entry.key,
                reason=f"auto: flip_rate={entry.flip_rate}",
                flip_rate=entry.flip_rate,
            ))
    return added
