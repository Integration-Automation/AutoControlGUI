"""One background task at a time for a tab, with a Stop that reaches a running script.

The tabs' commands used to run on the GUI thread: executing an action list,
asking a VLM, pushing a file. :class:`TabTask` is the small piece every such
tab shares on top of :mod:`je_auto_control.gui.task_controller`:

* **One run at a time.** :meth:`TabTask.start` refuses while a task is
  running, so a second click (or a script that clicks this window's own Run
  action) does not start a nested run.
* **Outcomes on the GUI thread.** ``result`` / ``error`` / ``finished`` are
  relayed from the task's handle; :attr:`TabTask.tag` says which command the
  outcome belongs to. :attr:`TabTask.task` is ``None`` again before
  ``finished`` is emitted.
* **Stop.** A script run (:meth:`TabTask.start_script`) is a stoppable
  executor run: :meth:`TabTask.stop` requests the stop and returns at once --
  it never waits for the worker, so a script that drives this GUI cannot
  deadlock it -- and the run's end arrives as an ``ExecutionStopped`` error
  once the worker has really unwound, which is when the tab is free again.
  Other work is cancelled through its handle: it runs to its end unobserved
  and its result is dropped.

The object keeps no reference to its tab beyond Qt parentage, and the work it
is given must not hold a widget (the controller refuses it): read what the
work needs from the widgets first and pass plain values.
"""
import functools
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Signal

from je_auto_control.gui.task_controller import CancellationToken, TaskHandle, task_controller
from je_auto_control.utils.executor.run_control import (
    ExecutionStopped, StopToken, stop_execution, stoppable_run,
)


class TabTask(QObject):
    """Runs one piece of background work at a time for its parent widget."""

    result = Signal(object)
    error = Signal(object)
    finished = Signal()

    def __init__(self, owner: QObject) -> None:
        super().__init__(owner)
        self.task: Optional[TaskHandle] = None
        self.tag = ""
        self._stop_token: Optional[StopToken] = None

    @property
    def running(self) -> bool:
        """Whether a task was started and its outcome has not arrived yet."""
        return self.task is not None

    @property
    def stopping(self) -> bool:
        """Whether the running script was asked to stop and is still unwinding."""
        return self.task is not None and self._stop_token is not None and self._stop_token.stopped

    def start(self, work: Callable[[], Any], *, tag: str = "", timeout_s: Optional[float] = None,
              discard: Optional[Callable[[Any], object]] = None) -> bool:
        """Run ``work()`` off the GUI thread; return ``False`` when a task is already running."""
        if self.task is not None:
            return False
        self._submit(functools.partial(_call_plain, work), tag, timeout_s, discard)
        return True

    def start_script(self, work: Callable[[], Any], *, tag: str = "") -> bool:
        """Run ``work()`` as a stoppable executor run; ``False`` when one is already running."""
        if self.task is not None:
            return False
        self._stop_token = StopToken()
        self._submit(functools.partial(_call_stoppable, self._stop_token, work), tag, None, None)
        return True

    def stop(self) -> bool:
        """Stop the running script, or cancel other work; return whether anything was running.

        Never blocks. A script ends at its next checkpoint and reports
        ``ExecutionStopped`` through :attr:`error`; calling this again while
        it unwinds also interrupts the script's own cleanup.
        """
        if self.task is None:
            return False
        if self._stop_token is not None:
            self._stop_token.stop("stopped from the GUI")
            return True
        return self.task.cancel()

    def _submit(self, work: Callable[[CancellationToken], Any], tag: str,
                timeout_s: Optional[float], discard: Optional[Callable[[Any], object]]) -> None:
        self.tag = tag
        handle = task_controller().submit(work, owner=self.parent(), timeout_s=timeout_s, discard=discard)
        self.task = handle
        handle.result.connect(self.result)
        handle.error.connect(self.error)
        handle.finished.connect(self._on_finished)

    def _on_finished(self) -> None:
        self.task = None
        self._stop_token = None
        self.finished.emit()


def _call_plain(work: Callable[[], Any], _token: CancellationToken) -> Any:
    """Worker thread: work that takes neither a timeout nor a cancel signal."""
    return work()


def _call_stoppable(stop: StopToken, work: Callable[[], Any], token: CancellationToken) -> Any:
    """Worker thread: run ``work`` inside a stoppable run bound to ``stop``."""
    # The tab was destroyed, or the application is exiting: stop the script too.
    token.on_cancel(stop.stop)
    with stoppable_run(token=stop):
        return work()


def stop_all_script_runs() -> int:
    """Ask every stoppable run in this process to stop (the window's Ctrl+4)."""
    return stop_execution(reason="stopped from the GUI")


def was_stopped(error: object) -> bool:
    """Whether a task's error is the script having been stopped."""
    return isinstance(error, ExecutionStopped)


__all__ = ["TabTask", "stop_all_script_runs", "was_stopped"]
