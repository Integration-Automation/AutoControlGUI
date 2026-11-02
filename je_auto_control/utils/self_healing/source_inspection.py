"""Bounded original-step inspection using captured self-healing journal provenance."""
from pathlib import Path
from typing import Callable, Optional

from je_auto_control.utils.action_journal.inspection import inspect_journal
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.self_healing.requests import SelfHealRequestError


def inspect_heal_source(path: str | Path, run_id: str, step_id: str, *, limit: int = 100,
                         observer: Optional[Callable[[int], None]] = None,
                         path_policy: Optional[PathPolicy] = None) -> list[dict[str, object]]:
    """Read sanitized snapshots for one captured run/step, without replaying it.

    Pass journal_path, run_id and step_id from a healing event. Legacy or
    uncaptured records do not have a source path; missing identifiers are
    rejected before I/O. Filtering precedes the limit, but the whole journal
    is validated. Current roots apply, including changes during progress.
    """
    for value in (run_id, step_id):
        if not isinstance(value, str) or not value or "\x00" in value:
            raise SelfHealRequestError("captured journal run and step IDs are required")
    if not isinstance(path, (str, Path)) or not str(path) or "\x00" in str(path):
        raise SelfHealRequestError("captured journal path is required")
    return inspect_journal(path, run_id=run_id, step_id=step_id, limit=limit,
                            observer=observer, path_policy=path_policy)


def _read_heal_source_command(path: str, run_id: str, step_id: str, limit: int = 100) -> list[dict[str, object]]:
    """Inspect one original step through a JSON-safe command signature."""
    return inspect_heal_source(path, run_id, step_id, limit=limit)
