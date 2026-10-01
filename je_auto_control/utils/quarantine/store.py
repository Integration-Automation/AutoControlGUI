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

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union

from je_auto_control.utils.json_store.json_store import SharedJsonDict
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


_T = TypeVar("_T")


def _default_path() -> Path:
    return Path.home() / ".je_auto_control" / "quarantine.json"


def _timestamp(value: Any) -> float:
    """``added_at`` as a float; an unreadable one reads as 0.0."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse(raw: Dict[str, Any], path: Path) -> Dict[str, QuarantineEntry]:
    """The valid entries of a quarantine file's contents, by name."""
    entries = raw.get("entries")
    if entries is None:
        return {}
    if not isinstance(entries, list):
        autocontrol_logger.warning("quarantine file %s ignored: entries is not a list", path)
        return {}
    parsed: Dict[str, QuarantineEntry] = {}
    for item in entries:
        # One malformed entry (a null ``added_at``, a list as the name)
        # used to crash the store -- and every suite run that consults it.
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) \
                or not item["name"]:
            continue
        parsed[item["name"]] = QuarantineEntry(
            name=item["name"], reason=str(item.get("reason", "")),
            added_at=_timestamp(item.get("added_at")),
            flip_rate=item.get("flip_rate"),
        )
    return parsed


class QuarantineStore:
    """JSON-backed set of quarantined case names, shared by every process using the file.

    Each change takes the file's lock, re-reads it and writes it back
    atomically, and each read reads it afresh. The store used to load the
    file once and write its own copy back on every change, so a long-running
    runner holding the default store wiped names the CLI or GUI had added.
    """

    def __init__(self, path: Union[str, Path, None] = None) -> None:
        self._path = Path(path) if path is not None else _default_path()
        self._state = SharedJsonDict(self._path)

    @property
    def path(self) -> str:
        return str(self._path)

    def _entries(self) -> Dict[str, QuarantineEntry]:
        return _parse(self._state.read(), self._path)

    def _change(self, mutate: Callable[[Dict[str, QuarantineEntry]], _T]) -> _T:
        """Apply ``mutate`` to the current entries and save them."""
        def apply(data: Dict[str, Any]) -> _T:
            entries = _parse(data, self._path)
            result = mutate(entries)
            data.clear()
            data["entries"] = [entry.to_dict() for entry in entries.values()]
            return result
        return self._state.update(apply)

    def add(self, name: str, reason: str = "",
            flip_rate: Optional[float] = None) -> QuarantineEntry:
        """Quarantine ``name`` (idempotent); return the stored entry."""
        if not name:
            raise ValueError("quarantine name must be non-empty")
        entry = QuarantineEntry(name=name, reason=reason, added_at=time.time(),
                                flip_rate=flip_rate)
        self._change(lambda entries: entries.__setitem__(name, entry))
        return entry

    def remove(self, name: str) -> bool:
        """Release ``name`` from quarantine; return False if absent."""
        return self._change(lambda entries: entries.pop(name, None) is not None)

    def is_quarantined(self, name: str) -> bool:
        """Whether ``name`` is quarantined now (read afresh)."""
        return name in self._entries()

    def names(self) -> Set[str]:
        """The quarantined names (read afresh)."""
        return set(self._entries())

    def list(self) -> List[QuarantineEntry]:
        """The quarantined entries by name (read afresh)."""
        return sorted(self._entries().values(), key=lambda e: e.name)

    def clear(self) -> int:
        """Release every name; return how many were quarantined."""
        def wipe(entries: Dict[str, QuarantineEntry]) -> int:
            count = len(entries)
            entries.clear()
            return count
        return self._change(wipe)


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
