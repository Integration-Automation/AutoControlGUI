"""Capture error-time screenshots and attach them to run-history rows.

The snapshot is stored under ``~/.je_auto_control/artifacts/`` and its path
is written back into the ``runs.artifact_path`` column so the GUI / REST
surfaces can surface it alongside the failure reason.
"""
import time
from pathlib import Path
from typing import Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.history_store import (
    HistoryStore, default_history_store,
)

_ARTIFACTS_DIRNAME = "artifacts"


def default_artifacts_dir() -> Path:
    """Return the per-user directory that holds error-time snapshots."""
    return Path.home() / ".je_auto_control" / _ARTIFACTS_DIRNAME


def capture_error_snapshot(run_id: int,
                           artifacts_dir: Optional[Path] = None,
                           store: Optional[HistoryStore] = None,
                           ) -> Optional[str]:
    """Screenshot the full screen and attach the file to ``run_id``.

    Returns the absolute file path on success, ``None`` if the capture
    failed (no display, missing backend, disk error). Errors are
    swallowed and logged — a crashing artifact step must not mask the
    original failure the caller is trying to record.
    """
    target_dir = Path(artifacts_dir) if artifacts_dir is not None \
        else default_artifacts_dir()
    target = target_dir / f"run_{int(run_id)}_{int(time.time() * 1000)}.png"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        from je_auto_control.wrapper.auto_control_screen import screenshot
        screenshot(str(target))
    except (OSError, ValueError, RuntimeError) as error:
        autocontrol_logger.warning(
            "error-snapshot for run %d failed: %r", int(run_id), error,
        )
        return None
    if not target.exists():
        return None
    bound_store = store if store is not None else default_history_store
    bound_store.attach_artifact(int(run_id), str(target))
    return str(target)


__all__ = ["capture_error_snapshot", "default_artifacts_dir"]
