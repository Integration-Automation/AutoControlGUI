"""Explicit manual execution ownership without changing executor results or variables."""
from contextlib import contextmanager
from typing import Iterator, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.logging.secret_scope import scrub_secret_text, secret_log_scope
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.context import HistoryBinding, bound_history
from je_auto_control.utils.run_history.history_store import (
    HistoryStore, HistoryStoreError, SOURCE_MANUAL, STATUS_ERROR, default_history_store,
)
from je_auto_control.utils.run_history.run_outcome import RunOutcome


@contextmanager
def manual_history_scope(*, store: Optional[HistoryStore] = None, source_id: str = "manual",
                         script_path: str = "<manual>") -> Iterator[HistoryBinding]:
    """Record an explicitly requested manual run, preserving the caller's execution scope.

    The yielded binding identifies one new history row. Existing and nested
    journals link to it; leaving restores the previous owner. Executor-counted
    failures mark the row as error without changing results or raising a new
    exception. Normal break/continue signals retain the counted outcome.
    Domain result flags remain the caller's responsibility. No
    screenshot is requested. SQLite is needed only when this scope is entered.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: the executor imports manual command adapters
    from je_auto_control.utils.executor.action_executor import recorded_failures
    # pylint: disable-next=import-outside-toplevel  # reason: flow control imports the capture/history boundary
    from je_auto_control.utils.executor.flow_control import LoopBreak, LoopContinue
    with secret_log_scope():
        authorize_command("AC_history_capture")
        for value in (source_id, script_path):
            if not isinstance(value, str) or not value:
                raise HistoryStoreError("manual history labels must be non-empty strings")
        owner = default_history_store if store is None else store
        identity = owner.start_run(SOURCE_MANUAL, scrub_secret_text(source_id), scrub_secret_text(script_path))
        binding = HistoryBinding(owner, identity)
        outcome, error, before = RunOutcome(), None, recorded_failures()
        with bound_history(binding):
            try:
                _link_current_journal(binding)
                yield binding
            except BaseException as failure:  # reason: record and re-raise the exact original control signal
                error = failure
                if not isinstance(failure, (LoopBreak, LoopContinue)):
                    outcome.fail(failure)
                raise
            finally:
                failures = recorded_failures() - before
                if failures > 0 and outcome.status != STATUS_ERROR:
                    outcome.status = STATUS_ERROR
                    outcome.error_text = f"{failures} action(s) failed; see this run's record"
                _finish(binding, outcome, error)


def _link_current_journal(owner: HistoryBinding) -> None:
    """Include a capture that was opened before its new manual history owner."""
    # pylint: disable-next=import-outside-toplevel  # reason: capture imports the history package during facade setup
    from je_auto_control.utils.action_journal.capture import current_journal
    capture = current_journal()
    if capture is None:
        return
    path = str(capture.journal.path.resolve())
    if any(scrub_secret_text(value) != value for value in (path, capture.run_id)):
        raise HistoryStoreError("active journal provenance cannot contain a resolved secret")
    for policy in capture.path_policies:
        policy.validate(path, operation="manual history journal link")
    if not owner.store.attach_journal(owner.run_id, path, capture.run_id):
        raise HistoryStoreError("cannot attach journal to a missing manual history run")


def _finish(owner: HistoryBinding, outcome: RunOutcome, error: Optional[BaseException]) -> None:
    """Preserve a pending original failure if final metadata cannot be committed."""
    try:
        if not owner.store.finish_run(owner.run_id, outcome.status, outcome.error_text):
            raise HistoryStoreError("cannot finish a missing manual history run")
    except BaseException:  # pylint: disable=broad-exception-caught  # reason: retain the pending original signal
        if error is None:
            raise
        autocontrol_logger.error("manual history completion unavailable; preserving original exception")
