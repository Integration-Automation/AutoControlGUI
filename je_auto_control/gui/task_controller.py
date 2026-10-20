"""Cooperative GUI tasks with inert outcomes, refreshed context and owner-bound delivery."""
from __future__ import annotations

from contextvars import copy_context
from dataclasses import dataclass
from functools import partial
from threading import Event
from typing import Callable, Literal, Optional, cast
import weakref

from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QThread, Signal, SignalInstance

from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.utils.exception.cancellation import CancellationToken, TaskProgress
from je_auto_control.utils.exception.control_signals import is_run_interruption, raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_text
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


@dataclass(frozen=True)
class TaskOutcome:
    """One terminal observation; failures carry text instead of exception objects or tracebacks."""

    task_id: int
    status: Literal['ok', 'cancelled', 'error']
    value: object = None
    error: str = ''
    control: str = ''


@dataclass
class _TaskState:
    token: CancellationToken
    owner_alive: Event
    handle_alive: Event
    worker: Optional[WorkerHandle] = None
    owner_connection: Optional[QMetaObject.Connection] = None


def _watch_destruction(owner: QObject, callback: Callable[..., None]) -> QMetaObject.Connection:
    return cast(QMetaObject.Connection, cast(SignalInstance, owner.destroyed).connect(callback))


def _require_gui_thread(owner: QObject) -> None:
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() is not app.thread() or owner.thread() is not app.thread():
        raise AutoControlException('task lifecycle operations must belong to the GUI thread')


def _owner_died(state: _TaskState, *_args: object) -> None:
    state.owner_alive.clear()
    state.token.cancel()


def _handle_died(state: _TaskState, *_args: object) -> None:
    state.handle_alive.clear()
    state.token.cancel()


def _close_jobs(jobs: dict[int, _TaskState], *_args: object) -> None:
    for state in tuple(jobs.values()):
        _owner_died(state)


def _retire(jobs: dict[int, _TaskState], task_id: int, state: _TaskState, *_args: object) -> None:
    jobs.pop(task_id, None)
    state.worker = None
    if state.owner_connection is not None:
        QObject.disconnect(state.owner_connection)
        state.owner_connection = None


def _deliver(handle_ref: weakref.ReferenceType[TaskHandle], state: _TaskState, outcome: TaskOutcome) -> None:
    handle = handle_ref()
    if handle is not None and state.owner_alive.is_set() and state.handle_alive.is_set():
        handle.complete(outcome)


def _failed_outcome(task_id: int, error: BaseException) -> TaskOutcome:
    try:
        control = _interruption_name(error)
        if control:
            return TaskOutcome(task_id, 'cancelled', control=control)
        detail, control = _error_detail(error)
        if control:
            return TaskOutcome(task_id, 'cancelled', control=control)
        return TaskOutcome(task_id, 'error', error=scrub_secret_text(detail))
    finally:
        _clear_tracebacks(error)


def _interruption_name(error: BaseException) -> str:
    try:
        raise_caused_run_interruption(error)
    # pylint: disable-next=broad-exception-caught  # reason: an async outcome replaces cross-thread exception retention
    except BaseException as control:  # reason: classify hard controls without retaining their traceback or logging
        if is_run_interruption(control):
            return type(control).__name__
    return ''


def _error_detail(error: BaseException) -> tuple[str, str]:
    try:
        return repr(error), ''
    # pylint: disable-next=broad-exception-caught  # reason: exception formatting cannot escape the task boundary
    except BaseException as failure:  # reason: retain a formatting interruption as cancellation, otherwise omit detail
        control = _interruption_name(failure)
        _clear_tracebacks(failure)
        return f'{type(error).__name__}: exception detail unavailable', control


def _clear_tracebacks(error: BaseException) -> None:
    pending, seen = [error], set[int]()
    while pending and len(seen) < 64:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        current.__traceback__ = None
        pending.extend(cause for cause in (current.__cause__, current.__context__) if cause is not None)


def _publish_progress(worker_ref: weakref.ReferenceType[_TaskWorker], progress: TaskProgress) -> None:
    worker = worker_ref()
    if worker is not None:
        worker.progress.emit(TaskProgress(progress.task_id, progress.completed, progress.total,
                                          scrub_secret_text(progress.detail)))


class _TaskWorker(QObject):
    finished = Signal(object)
    progress = Signal(object)

    def __init__(self, task_id: int, work: Callable[[CancellationToken], object]) -> None:
        super().__init__()
        self._task_id = task_id
        self._work = work
        self.token = CancellationToken(task_id, partial(_publish_progress, weakref.ref(self)))
        self._context = copy_context()
        self._authority = DeferredAuthorization.capture()

    def request_stop(self) -> None:
        """Participate in the existing worker registry's bounded interpreter-exit grace."""
        self.token.cancel()

    def run(self) -> None:
        """Run under the submission context and emit one inert terminal outcome."""
        self.finished.emit(self._context.run(self._perform))

    def _perform(self) -> TaskOutcome:
        try:
            self.token.checkpoint()
            with self._authority.context_scope():
                value = self._work(self.token)
        # pylint: disable-next=broad-exception-caught  # reason: this is the worker's terminal containment boundary
        except BaseException as error:  # reason: emit typed failure/cancellation without retaining thread tracebacks
            return _failed_outcome(self._task_id, error)
        # A successful operation may have committed; a late stop cannot rewrite that fact.
        return TaskOutcome(self._task_id, 'ok', value=value)


class TaskHandle(QObject):
    """Caller-owned task observations; delivery ceases when its owner or handle is destroyed."""

    finished = Signal(object)
    progress = Signal(object)

    def __init__(self, task_id: int, state: _TaskState) -> None:
        super().__init__()
        self.task_id = task_id
        self._state = state
        self._outcome: Optional[TaskOutcome] = None
        _watch_destruction(self, partial(_handle_died, state))

    @property
    def outcome(self) -> Optional[TaskOutcome]:
        """The delivered terminal observation, or None while pending or abandoned."""
        return self._outcome

    @property
    def is_running(self) -> bool:
        """Whether the underlying daemon worker is still running."""
        return self._state.worker is not None and self._state.worker.isRunning()

    @property
    def is_cancelled(self) -> bool:
        """Whether a cooperative stop has been requested."""
        return self._state.token.is_cancelled

    def cancel(self) -> None:
        """Request stop; the worker's checkpoints and finally blocks own cleanup."""
        self._state.token.cancel()

    def complete(self, outcome: TaskOutcome) -> None:
        """Deliver once on the GUI thread, after the controller's lifetime checks."""
        _require_gui_thread(self)
        if (self._outcome is None and outcome.task_id == self.task_id
                and self._state.owner_alive.is_set() and self._state.handle_alive.is_set()):
            self._outcome = outcome
            self.finished.emit(outcome)

    def forward_progress(self, progress: TaskProgress) -> None:
        """Relay inert progress on the GUI thread while this task's owner is alive."""
        _require_gui_thread(self)
        if (progress.task_id == self.task_id and self._outcome is None
                and self._state.owner_alive.is_set() and self._state.handle_alive.is_set()):
            self.progress.emit(progress)


class TaskController(QObject):
    """Submit GUI work without retaining owners; work must authorize its own operation."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        _require_gui_thread(self)
        self._jobs: dict[int, _TaskState] = {}
        self._next_id = 0
        self._closed = False
        _watch_destruction(self, partial(_close_jobs, self._jobs))

    @property
    def active_count(self) -> int:
        """How many jobs have not yet been retired on the GUI thread."""
        return len(self._jobs)

    def submit(self, work: Callable[[CancellationToken], object], *, owner: QObject) -> TaskHandle:
        """Start one independent task on the GUI thread, capturing its registrant's context."""
        self._require_gui_owner(owner)
        if self._closed:
            raise AutoControlException('this task controller is closed')
        self._next_id += 1
        task_id = self._next_id
        worker = _TaskWorker(task_id, work)
        state = _TaskState(worker.token, Event(), Event())
        state.owner_alive.set()
        state.handle_alive.set()
        handle = TaskHandle(task_id, state)
        state.owner_connection = _watch_destruction(owner, partial(_owner_died, state))
        worker.progress.connect(handle.forward_progress)
        self._jobs[task_id] = state
        retire = partial(_retire, self._jobs, task_id, state)
        _watch_destruction(worker, retire)
        try:
            state.worker = start_worker(self, worker, on_done=partial(_deliver, weakref.ref(handle), state),
                                        on_thread_done=retire)
        except BaseException:  # reason: roll back this submission before preserving a failed-start control
            _owner_died(state)
            retire()
            handle.deleteLater()
            raise
        return handle

    def close(self) -> None:
        """Stop accepting work, abandon delivery and request every active job to stop."""
        _require_gui_thread(self)
        self._closed = True
        _close_jobs(self._jobs)

    def _require_gui_owner(self, owner: QObject) -> None:
        _require_gui_thread(self)
        _require_gui_thread(owner)


__all__ = ['CancellationToken', 'TaskController', 'TaskHandle', 'TaskOutcome', 'TaskProgress']
