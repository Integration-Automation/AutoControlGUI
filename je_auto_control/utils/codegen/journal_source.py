"""Bounded immutable journal snapshots with strict schema, ordering and current-root checks."""
import io
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterator, Optional

from je_auto_control.utils.action_journal.events import ActionEvent
from je_auto_control.utils.action_journal.inspection import _checked_path
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError
from je_auto_control.utils.path_guard.policy import PathPolicy

MAX_SOURCE_BYTES = 64 * 1024 * 1024
_MAX_RECORD_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class JournalRow:
    """One validated event and its actual one-based source line."""

    event: ActionEvent
    line: int


@dataclass(frozen=True)
class JournalSource:
    """Selected rows from one bounded byte snapshot, with whole-source identity."""

    path: Path
    sha256: str
    rows: tuple[JournalRow, ...]
    record_count: int
    torn_tail: bool


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON object keys, including nested input parameters."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateGenerationError("duplicate journal JSON key")
        result[key] = value
    return result


def load_source(path: str | Path, run_id: str, observer: Optional[Callable[[int], None]],
                  policy: Optional[PathPolicy]) -> JournalSource:
    """Validate the entire source before selecting rows; callbacks may cancel without a partial result."""
    if not isinstance(run_id, str) or not run_id or "\x00" in run_id:
        raise CandidateGenerationError("run_id must be non-empty text")
    if observer is not None:
        observer(0)
    source = _checked_path(path, policy)

    def checkpoint(count: int) -> None:
        check_source_path(source, policy)
        if observer is not None:
            observer(count)
        check_source_path(source, policy)

    checkpoint(0)
    with source.open("rb") as handle:
        data = handle.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise CandidateGenerationError("journal source exceeds 64 MiB")
    selected, count = [], 0
    for row in _rows(data):
        count += 1
        if count > 100000:
            raise CandidateGenerationError("journal source exceeds 100000 records")
        checkpoint(count)
        if row.event.run_id == run_id:
            selected.append(row)
    checkpoint(count)
    if not selected:
        raise CandidateGenerationError("journal has no records for the selected run")
    return JournalSource(source, sha256(data).hexdigest(), tuple(selected), count, not data.endswith(b"\n"))


def check_source_path(path: Path, policy: Optional[PathPolicy]) -> None:
    """Preserve the canonical binding as current and enclosing roots change."""
    if _checked_path(path, policy) != path:
        raise CandidateGenerationError("journal source binding changed")


def _rows(data: bytes) -> Iterator[JournalRow]:
    previous, count = 0, 0
    with io.BytesIO(data) as handle:
        while True:
            raw = handle.readline(_MAX_RECORD_BYTES + 2)
            if len(raw) > _MAX_RECORD_BYTES + 1:
                raise CandidateGenerationError("journal record exceeds 8 MiB")
            if not raw.endswith(b"\n"):
                if raw and count == 0:
                    raise CandidateGenerationError("journal has no committed first record")
                return
            count += 1
            event = _decode(raw, count)
            if event.sequence <= previous:
                raise CandidateGenerationError(f"unordered journal record at line {count}")
            previous = event.sequence
            yield JournalRow(event, count)


def _decode(raw: bytes, line: int) -> ActionEvent:
    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
        return ActionEvent.from_dict(payload)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CandidateGenerationError(f"invalid journal record at line {line}") from None
