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
from typing import Any, Callable

from je_auto_control.utils.exception.exceptions import AutoControlActionException


def run_counting_failures(run: Callable[[], Any]) -> Any:
    """Run in fresh variables and count new failures without resetting the caller.

    Manual observer/watchdog polls may run inside another action list. Resetting
    the thread's counter here erased that caller's previous failures and could
    make the CLI report success. A per-run delta keeps both outcomes intact.
    """
    from je_auto_control.utils.executor.action_executor import (
        recorded_failures,
    )
    from je_auto_control.utils.script_vars.execution import execution_scope
    before = recorded_failures()
    with execution_scope():
        result = run()
    failures = recorded_failures() - before
    if failures:
        raise AutoControlActionException(
            f"{failures} action(s) failed; see this run's record for which")
    return result
