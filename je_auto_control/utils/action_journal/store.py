"""Append-only JSON-lines store for :class:`ActionEvent` records.

A started action is written at once as a whole ``start`` line with status
``incomplete``; how it ended follows as a short ``end`` line. Reading folds
the two together, so an action whose end never reached the file -- the
process died, the run was interrupted -- reads back as ``incomplete`` instead
of looking like a success. Lines are parsed with ``json`` only.

Pure standard library; imports no ``PySide6``.
"""
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from je_auto_control.utils.action_journal.events import (
    RECORD_END, STATUS_ERROR, STATUS_INCOMPLETE, STATUS_OK, ActionEvent,
    JournalFormatError, apply_end, check_record, event_from_dict,
)
from je_auto_control.utils.json_store.json_store import append_json_line


def default_journal_path() -> Path:
    """``~/.je_auto_control/action_journal.jsonl``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "action_journal.jsonl"


class ActionJournal:
    """Thread-safe append-only journal file. Appending creates it."""

    def __init__(self, path: Union[str, Path, None] = None) -> None:
        self._path = Path(path) if path is not None else default_journal_path()
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        """The file this journal appends to."""
        return self._path

    def append(self, event: ActionEvent) -> None:
        """Append ``event`` as one whole line (the start of an action)."""
        self._write(event.to_dict())

    def append_end(self, event: ActionEvent) -> None:
        """Append how the already-written ``event`` ended."""
        self._write(event.end_dict())

    def _write(self, record: Dict[str, Any]) -> None:
        # default=str is never reached for a sanitised event; it only keeps a
        # hand-built one from raising half-way through a run.
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            append_json_line(self._path, line)

    def read(self, *, run_id: Optional[str] = None) -> List[ActionEvent]:
        """The events of this journal, in the order they started."""
        return read_events(self._path, run_id=run_id)


@dataclass(frozen=True)
class JournalContents:
    """What a journal file holds: the folded events and what could not be read."""

    events: Tuple[ActionEvent, ...]
    #: ``step_id`` -> 1-based line number of the event's ``start`` line.
    lines: Dict[str, int] = field(default_factory=dict)
    #: 1-based numbers of lines that are not JSON (a write cut off mid-line).
    torn_lines: Tuple[int, ...] = ()


def _fold(path: Path, run_id: Optional[str]) -> JournalContents:
    """Parse every line of ``path`` and fold ``end`` lines into their starts."""
    events: Dict[Tuple[str, str], ActionEvent] = {}
    lines: Dict[str, int] = {}
    torn: List[int] = []
    # The journal path is the operator's own (start_action_journal / --from-log).
    with path.open("r", encoding="utf-8", errors="replace") as handle:  # NOSONAR pythonsecurity:S8707
        for number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            where = f"{path.name} line {number}"
            try:
                data = json.loads(raw)
            except ValueError:
                torn.append(number)
                continue
            record = check_record(data, where)
            if run_id is not None and data["run_id"] != run_id:
                continue
            key = (data["run_id"], data["step_id"])
            if record == RECORD_END:
                # An end whose start is missing has nothing to describe.
                if key in events:
                    events[key] = apply_end(events[key], data, where)
                continue
            if key in events:
                raise JournalFormatError(f"{where}: step {key[1]!r} is recorded twice")
            events[key] = event_from_dict(data, where)
            lines[key[1]] = number
    return JournalContents(tuple(events.values()), lines, tuple(torn))


def load_journal(path: Union[str, Path], *, run_id: Optional[str] = None
                 ) -> JournalContents:
    """Read ``path`` with line numbers and the torn lines it skipped.

    A line that is not JSON is skipped and reported (an append cut off by a
    crash is expected in an append-only file); a JSON line that is not a
    journal record of this schema raises :class:`JournalFormatError`.
    """
    file_path = Path(os.path.realpath(os.fspath(path)))
    if not file_path.is_file():
        raise JournalFormatError(f"no journal file at {file_path}")
    return _fold(file_path, run_id)


def read_events(path: Union[str, Path], *, run_id: Optional[str] = None
                ) -> List[ActionEvent]:
    """The events in the journal at ``path``, in the order they started.

    ``run_id`` keeps one run's events. An action with no recorded end has
    status ``incomplete``.
    """
    return list(load_journal(path, run_id=run_id).events)


def list_journal_runs(path: Union[str, Path]) -> List[Dict[str, Any]]:
    """One summary per run in the journal at ``path``, oldest first."""
    runs: Dict[str, Dict[str, Any]] = {}
    for event in load_journal(path).events:
        run = runs.setdefault(event.run_id, {
            "run_id": event.run_id, "session": event.session,
            "started_at": event.started_at, "finished_at": None, "events": 0,
            STATUS_OK: 0, STATUS_ERROR: 0, STATUS_INCOMPLETE: 0,
        })
        run["events"] += 1
        run[event.status] += 1
        if event.finished_at is not None:
            run["finished_at"] = max(run["finished_at"] or 0.0, event.finished_at)
    return list(runs.values())
