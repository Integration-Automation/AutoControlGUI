"""Sanitized, bounded journal snapshots shared by operation surfaces."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from je_auto_control.utils.action_journal.events import ActionJournalError
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.action_journal.store import read_events
from je_auto_control.utils.path_guard.path_guard import validate_path
from je_auto_control.utils.path_guard.policy import PathPolicy


def inspect_journal(path: str | Path, *, run_id: Optional[str] = None, limit: int = 100,
                     observer: Optional[Callable[[int], None]] = None,
                     path_policy: Optional[PathPolicy] = None,
                     step_id: Optional[str] = None) -> list[dict[str, object]]:
    """Validate a whole journal, then return at most ``limit`` sanitized snapshots.

    Run/step filtering precedes the 1–10,000 output limit; validation still loads the
    whole file. Start/completion snapshots stay separate, and missing files
    return an empty list. The source is never modified. The default path-root
    guard applies, unlike the low-level ``read_events`` storage reader.
    Enclosing captured roots and an explicit policy intersect. The observer
    sees every validated record count before filtering and may cancel reading.
    """
    _check_selection(limit, step_id)
    candidate = _checked_path(path, path_policy)

    def checkpoint(count: int) -> None:
        _checked_path(candidate, path_policy)
        if observer is not None:
            observer(count)
        _checked_path(candidate, path_policy)

    events = read_events(candidate, run_id=run_id, observer=checkpoint)
    _checked_path(candidate, path_policy)
    if step_id is not None:
        events = [event for event in events if event.step_id == step_id]
    return [sanitize_event(event) for event in events[:limit]]


def _check_selection(limit: int, step_id: Optional[str]) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ActionJournalError("journal limit must be an integer from 1 to 10000")
    if step_id is not None and (not isinstance(step_id, str) or not step_id or "\x00" in step_id):
        raise ActionJournalError("journal step ID must be non-empty text or null")


def _checked_path(path: str | Path, path_policy: Optional[PathPolicy]) -> Path:
    # pylint: disable-next=import-outside-toplevel  # reason: package initialization imports this reader before capture
    from je_auto_control.utils.action_journal.capture import _effective_path_policies
    candidate = validate_path(path)
    for policy in _effective_path_policies(path_policy):
        candidate = policy.validate(candidate, operation="journal inspection")
    return candidate
