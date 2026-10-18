"""Sanitized, bounded journal snapshots shared by operation surfaces."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from je_auto_control.utils.action_journal.events import ActionJournalError
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.action_journal.store import read_events
from je_auto_control.utils.path_guard.path_guard import validate_path


def inspect_journal(path: str | Path, *, run_id: Optional[str] = None, limit: int = 100) -> list[dict[str, object]]:
    """Validate a whole journal, then return at most ``limit`` sanitized snapshots.

    Filtering precedes the 1–10,000 output limit; validation still loads the
    whole file. Start/completion snapshots stay separate, and missing files
    return an empty list. The source is never modified. The default path-root
    guard applies, unlike the low-level ``read_events`` storage reader.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ActionJournalError("journal limit must be an integer from 1 to 10000")
    events = read_events(validate_path(path), run_id=run_id)
    return [sanitize_event(event) for event in events[:limit]]
