"""Owner/run-bound GUI task delivery with cooperative cancellation and bounded deadlines."""
from __future__ import annotations

from functools import partial
from typing import Callable, Optional
import uuid
import weakref

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from shiboken6 import isValid  # pylint: disable=no-name-in-module  # reason: native binding exports this runtime API

from je_auto_control.gui._task_state import (
    CancellationToken, TaskCancelled, TaskControllerError, TaskError, TaskProgress, TaskResult, task_error,
)
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker, _INPUT_OWNERS, _owner_inputs
from je_auto_control.gui.tab_registry import _require_gui_thread
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.executor.request_context import RequestBinding
from je_auto_control.utils.executor.cancellation import _task_scope
from je_auto_control.utils.executor.input_owner import InputOwner, _input_scope


class _TaskWorker(CallWorker):
    """Daemon worker containing a headless callable/token and emitting only typed payloads."""

    progress = Signal(object)

    def __init__(self, work: Callable[[CancellationToken], object], run_id: str,
                 timeout_s: float, input_owner: InputOwner) -> None:
        super().__init__(lambda: None)
        self.token = CancellationToken(run_id, timeout_s, self.progress.emit)
        self._work = work
        self._binding = RequestBinding.capture()
        self._input_owner = input_owner

    def _execute(self) -> object:
        try:
            self.token.checkpoint()
            with _task_scope(self.token), _input_scope(self._input_owner, self.token.run_id):
                value = self._binding.run(partial(self._work, self.token))
            self.token.checkpoint()
            return TaskResult(self.token.run_id, value)
        except TaskCancelled:
            self.token.cancel()
            return None
        except Exception as failure:  # pylint: disable=broad-exception-caught  # reason: typed GUI boundary reports backend failures, preserving finally cleanup
            self._input_owner.request_cleanup(self.token.run_id)
            return task_error(self.token.run_id, failure)
        finally:
            if self.token.event.is_set():
                self._input_owner.request_cleanup(self.token.run_id)

    def run(self) -> None:
        """Execute without any widget references; result delivery is a GUI-thread relay."""
        self.finished.emit(self._execute())
        self.token.retire()

    def request_stop(self) -> None:
        """Allow the shared interpreter-exit worker registry to request cooperative stop."""
        self.token.cancel()


class TaskHandle(QObject):  # pylint: disable=too-many-instance-attributes  # reason: run identity, cancellation, outcome and owner/worker lifetime are distinct
    """Run-specific signals and state; cancellation drops delivery while cleanup completes."""

    completed = Signal(object)
    failed = Signal(object)
    progress = Signal(object)
    finished = Signal()

    def __init__(self, controller: TaskController, owner: QObject, worker: _TaskWorker) -> None:
        super().__init__(owner)
        self._controller = controller
        self._owner = weakref.ref(owner)
        self._owner_id = id(owner)
        self.token = worker.token
        self.run_id = self.token.run_id
        self.result: Optional[TaskResult] = None
        self.error: Optional[TaskError] = None
        self.state = 'busy'
        self._worker: Optional[WorkerHandle] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._expire)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        owner.destroyed.connect(self.token.cancel)
        self._owner_drop = partial(controller._drop_owner, self._owner_id, self.run_id)
        owner.destroyed.connect(self._owner_drop)
        worker.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)

    @property
    def is_running(self) -> bool:
        """Whether the backend has returned; cancelling does not force-stop Python threads."""
        return self._worker is not None and self._worker.isRunning()

    def isRunning(self) -> bool:  # pylint: disable=invalid-name  # reason: compatibility with legacy worker guards
        """Keep the existing GUI worker guard spelling while panels migrate."""
        return self.is_running

    def _current(self) -> bool:
        owner = self._owner()
        current = self._controller._active.get(self._owner_id, lambda: None)()  # pylint: disable=protected-access  # reason: same-module ownership
        return isValid(self) and owner is not None and isValid(owner) and current is self

    def _present(self, state: str, reason: str = '', progress: Optional[int] = None) -> None:
        owner = self._owner()
        if self._current() and owner is not None:
            owner.setProperty('execution_reason', reason)
            owner.setProperty('execution_progress', progress)
            owner.setProperty('execution_state', state)

    def cancel(self) -> None:
        """Request stop and suppress late completion; keep busy until owned cleanup returns."""
        _require_gui_thread()
        if self.state == 'busy':
            self.token.cancel()
            owner = self._owner()
            input_owner = _INPUT_OWNERS.get(owner) if owner is not None else None
            if input_owner is not None:
                input_owner.request_cleanup()
            self.state = 'cancelled'
            self._present('busy', language_wrapper.translate('workspace_cancelling'))

    def _expire(self) -> None:
        if self.state in ('busy', 'cancelled') and self.is_running:
            self.token.expire()
            owner = self._owner()
            input_owner = _INPUT_OWNERS.get(owner) if owner is not None else None
            if input_owner is not None:
                input_owner.request_cleanup()
            self.state = 'timed_out'
            self._present('busy', language_wrapper.translate('workspace_deadline_wait'))

    def _progress(self, value: TaskProgress) -> None:
        if self._current() and self.state == 'busy' and value.run_id == self.run_id:
            self._present('busy', value.message, value.percent)
            self.progress.emit(value)

    def _deliver(self, value: object) -> None:
        if not self._current() or self.token.event.is_set():
            return
        if isinstance(value, TaskResult) and value.run_id == self.run_id:
            self.result, self.state = value, 'ready'
            self._present('ready')
            self.completed.emit(value)
        elif isinstance(value, TaskError) and value.run_id == self.run_id:
            self.error, self.state = value, value.state
            self._present(value.state, value.message)
            self.failed.emit(value)

    def _crashed(self, message: str) -> None:
        self._deliver(TaskError(self.run_id, 'error', message))

    def _released(self) -> None:
        self._timer.stop()
        self.token.retire()
        if self.token.event.is_set():
            self.state = 'timed_out' if self.token.timed_out else 'cancelled'
            key = 'workspace_timed_out' if self.token.timed_out else 'workspace_cancelled'
            self._present('error' if self.token.timed_out else 'ready', language_wrapper.translate(key))
        current = self._current()
        if current:
            self._controller._active.pop(self._owner_id, None)  # pylint: disable=protected-access  # reason: same-module run retirement
        owner = self._owner()
        if owner is not None and isValid(owner):
            owner.destroyed.disconnect(self.token.cancel)
            owner.destroyed.disconnect(self._owner_drop)
        if current:
            self.finished.emit()
        self.setParent(None)
        self.deleteLater()


class TaskController:
    """Own one current run per QObject; replacing it cancels and invalidates the prior run."""

    def __init__(self, timeout_s: float = 30.0) -> None:
        self.timeout_s = timeout_s
        self._active: dict[int, weakref.ReferenceType[TaskHandle]] = {}

    def submit(self, work: Callable[[CancellationToken], object], *, owner: QObject) -> TaskHandle:
        """Snapshot request policy, then execute copied/headless inputs off the GUI thread."""
        _require_gui_thread()
        if not isinstance(owner, QObject) or not isValid(owner) or not callable(work):
            raise TaskControllerError('task requires a live QObject owner and callable work')
        if owner.thread() != QThread.currentThread():
            raise TaskControllerError('task owner must belong to the GUI application thread')
        input_owner = _owner_inputs(owner)
        worker = _TaskWorker(work, uuid.uuid4().hex, self.timeout_s, input_owner)
        if self.timeout_s * 1000 > 2147483647:
            raise TaskControllerError('task timeout exceeds the Qt timer range')
        previous = self._active.get(id(owner), lambda: None)()
        if previous is not None and isValid(previous):
            previous.cancel()
        handle = TaskHandle(self, owner, worker)
        self._active[id(owner)] = weakref.ref(handle)
        handle._present('busy')  # pylint: disable=protected-access  # reason: controller initializes its run handle
        # pylint: disable=protected-access  # reason: controller binds private lifecycle callbacks of its own handle
        handle._worker = start_worker(handle, worker, on_done=handle._deliver,
                                      on_thread_done=handle._released, on_fail=handle._crashed)
        handle._timer.start(max(1, int(self.timeout_s * 1000)))
        # pylint: enable=protected-access
        return handle

    def _drop_owner(self, owner_id: int, run_id: str, *_args: object) -> None:
        handle = self._active.get(owner_id, lambda: None)()
        if handle is not None and handle.run_id == run_id:
            self._active.pop(owner_id, None)

    def cancel_owner(self, owner: QObject) -> None:
        """Cancel the current run when a panel closes, even before QObject destruction."""
        _require_gui_thread()
        handle = self._active.get(id(owner), lambda: None)()
        if handle is not None and isValid(handle):
            handle.cancel()
        input_owner = _INPUT_OWNERS.get(owner)
        if input_owner is not None:
            input_owner.request_cleanup()


__all__ = ['TaskController', 'TaskHandle', 'CancellationToken', 'TaskResult', 'TaskError', 'TaskProgress']
