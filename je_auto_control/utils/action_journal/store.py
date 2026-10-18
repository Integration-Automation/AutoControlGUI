"""Append-only action JSONL with interprocess order and torn-tail recovery."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

from je_auto_control.utils.action_journal.events import ActionEvent, ActionJournalError
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.json_store.json_store import _file_lock, append_json_line

_MAX_RECORD_BYTES = 8 * 1024 * 1024


class ActionJournal:
    """Persist lifecycle snapshots in one ordered journal shared by writers.

    Each append redacts before acquiring a file handle, assigns sequence under
    the shared JSON-store lock, appends one complete line and fsyncs it. Only an
    unterminated crash fragment is discarded on recovery; committed lines stay.
    """

    def __init__(self, path: Path) -> None:
        try:
            self._path = Path(path)
        except (OSError, TypeError, ValueError):
            raise ActionJournalError("invalid action journal path") from None

    @property
    def path(self) -> Path:
        """The explicit journal destination; no global log is opened implicitly."""
        return self._path

    def append(self, event: ActionEvent) -> None:
        """Validate and sanitize an event before appending it durably."""
        event.validate()
        payload = sanitize_event(event)
        # Validate encoding/size before creating directories or lock files.
        _encode(payload)
        try:
            with _file_lock(self.path):
                payload["sequence"] = _next_sequence(self.path)
                append_json_line(self.path, _encode(payload))
                with self.path.open("ab") as handle:
                    os.fsync(handle.fileno())
        except (OSError, ValueError) as error:
            raise ActionJournalError("could not append action journal") from error


def _encode(payload: dict[str, object]) -> str:
    try:
        line = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        size = len(line.encode("utf-8"))
    except (TypeError, ValueError):
        raise ActionJournalError("invalid action journal payload encoding") from None
    if size > _MAX_RECORD_BYTES:
        raise ActionJournalError("action journal record exceeds 8 MiB")
    return line


def _next_sequence(path: Path) -> int:
    """Read only the tail, discarding an uncommitted fragment under the lock."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a+b") as handle:
        offset, tail = _tail(handle)
        if tail and not tail.endswith(b"\n"):
            boundary = tail.rfind(b"\n") + 1
            handle.truncate(offset + boundary)
            tail = tail[:boundary]
        if not tail:
            return 1
        raw = tail[:-1].rsplit(b"\n", 1)[-1]
        sequence = _decode(raw, 0).sequence + 1
        if sequence > 2 ** 63 - 1:
            raise ActionJournalError("action journal sequence exhausted")
        return sequence


def _tail(handle: BinaryIO) -> tuple[int, bytes]:
    position = handle.seek(0, os.SEEK_END)
    chunks: list[bytes] = []
    separators = total = 0
    while position > 0 and separators < 2:
        size = min(4096, position)
        position -= size
        handle.seek(position)
        chunk = handle.read(size)
        chunks.append(chunk)
        separators += chunk.count(b"\n")
        total += len(chunk)
        if total > 2 * _MAX_RECORD_BYTES + 4096:
            raise ActionJournalError("action journal tail exceeds record limit")
    return position, b"".join(reversed(chunks))


def _decode(raw: bytes, line_number: int) -> ActionEvent:
    try:
        payload: object = json.loads(raw.decode("utf-8"))
        return ActionEvent.from_dict(payload)
    except (ValueError, TypeError, UnicodeError):
        # Do not include raw data or JSON decoder messages: external journals
        # may contain secrets even though this writer never emits those bytes.
        raise ActionJournalError(f"invalid action journal record at line {line_number}") from None


def read_events(path: Path, *, run_id: Optional[str] = None) -> list[ActionEvent]:
    """Read validated snapshots in append order, optionally selecting one run.

    A final unterminated fragment is uncommitted and ignored. Malformed complete
    lines, unsupported schemas and non-increasing sequences are rejected. Start
    snapshots remain incomplete; reading never infers successful completion.
    """
    try:
        with Path(path).open("rb") as handle:
            return [event for event in _snapshots(handle) if run_id is None or event.run_id == run_id]
    except FileNotFoundError:
        return []
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, ActionJournalError):
            raise
        raise ActionJournalError("could not read action journal") from error


def _snapshots(handle: BinaryIO) -> Iterator[ActionEvent]:
    """Stream complete, bounded JSON lines and validate ordering across all runs."""
    previous = 0
    index = 0
    while True:
        line = handle.readline(_MAX_RECORD_BYTES + 2)
        if len(line) > _MAX_RECORD_BYTES + 1:
            raise ActionJournalError("action journal record exceeds 8 MiB")
        if not line.endswith(b"\n"):
            return  # EOF or the uncommitted final fragment
        index += 1
        event = _decode(line, index)
        if event.sequence <= previous:
            raise ActionJournalError(f"unordered action journal record at line {index}")
        previous = event.sequence
        yield event
