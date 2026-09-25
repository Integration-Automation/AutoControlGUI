"""Run a recorded job's actions and fail it if any of them failed.

``execute_action`` runs with ``raise_on_error=False``: a failed action (an
image or window not found) is recorded in the result and the run goes on, so
the scheduler, the trigger engine, the hotkey daemon and the webhook and
e-mail triggers recorded such runs as succeeded and took no error snapshot.
They run their actions through :func:`run_counting_failures`, which reads the
per-thread failure count ``je_auto_control run`` already uses for its exit code.
"""
from typing import Any, Callable

from je_auto_control.utils.exception.exceptions import AutoControlActionException


def run_counting_failures(run: Callable[[], Any]) -> Any:
    """Call ``run()``; raise if an action it executed was recorded as failed."""
    from je_auto_control.utils.executor.action_executor import (
        recorded_failures, reset_recorded_failures,
    )
    reset_recorded_failures()
    result = run()
    failures = recorded_failures()
    if failures:
        raise AutoControlActionException(
            f"{failures} action(s) failed; see this run's record for which")
    return result
