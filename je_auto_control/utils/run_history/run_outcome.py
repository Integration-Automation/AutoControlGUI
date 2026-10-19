"""Run a recorded job's actions and fail it if any of them failed.

``execute_action`` runs with ``raise_on_error=False``: a failed action (an
image or window not found) is recorded in the result and the run goes on, so
the scheduler, the trigger engine, the hotkey daemon and the webhook and
e-mail triggers recorded such runs as succeeded and took no error snapshot.
They run their actions through :func:`run_counting_failures`, which reads the
per-thread failure count ``je_auto_control run`` already uses for its exit code.

Each such run also gets its own variable scope: a job's ``AC_set_var`` used to
stay in the module executor for whichever job, trigger or hotkey fired next.
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.exception.control_signals import (
    is_run_interruption as is_run_interruption,
    raise_if_run_interrupted as raise_if_run_interrupted,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.history_store import HistoryStore, STATUS_ERROR, STATUS_OK
from je_auto_control.utils.script_vars.execution import execution_scope


@dataclass
class RunOutcome:
    """A run's final history state and permission to take an error snapshot."""

    status: str = STATUS_OK
    error_text: Optional[str] = None
    hard_abort: bool = False
    cancelled: bool = False

    def fail(self, error: BaseException) -> None:
        """Record failure without formatting a pending hard/cancellation signal."""
        self.status = STATUS_ERROR
        self.hard_abort = not isinstance(error, Exception)
        self.cancelled = is_run_interruption(error)
        self.error_text = (f"{type(error).__name__}: run interrupted" if self.hard_abort or self.cancelled
                           else _ordinary_error_text(error))

    @property
    def should_capture(self) -> bool:
        """Ordinary failures may capture; cancellation and hard exits may not."""
        return self.status == STATUS_ERROR and not self.hard_abort and not self.cancelled


def _ordinary_error_text(error: BaseException) -> str:
    """Keep a broken exception formatter from replacing the original run failure."""
    try:
        return repr(error)
    except Exception:  # pylint: disable=broad-exception-caught  # reason: preserve the original failure
        return f"{type(error).__name__}: exception detail unavailable"


def finish_history_run(store: HistoryStore, run_id: int, outcome: RunOutcome,
                       capture: Callable[[int], Optional[str]]) -> None:
    """Settle history while preserving any hard interruption already propagating."""
    artifact = capture(run_id) if outcome.should_capture else None
    try:
        store.finish_run(run_id, outcome.status, outcome.error_text, artifact_path=artifact)
    except Exception:  # pylint: disable=broad-exception-caught  # reason: preserve pending hard interruption
        if not outcome.hard_abort:
            raise
        autocontrol_logger.error("run history completion unavailable; preserving hard interruption")


def run_counting_failures(run: Callable[[], Any]) -> Any:
    """Run in fresh variables and count new failures without resetting the caller.

    Manual observer/watchdog polls may run inside another action list. Resetting
    the thread's counter here erased that caller's previous failures and could
    make the CLI report success. A per-run delta keeps both outcomes intact.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: executor imports this outcome helper
    from je_auto_control.utils.executor.action_executor import (
        recorded_failures,
    )
    before = recorded_failures()
    with execution_scope():
        result = run()
    failures = recorded_failures() - before
    if failures:
        raise AutoControlActionException(
            f"{failures} action(s) failed; see this run's record for which")
    return result
