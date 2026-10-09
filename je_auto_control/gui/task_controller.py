"""Cancellable background work for the GUI: typed outcomes on the GUI thread, nothing after the owner dies.

:func:`je_auto_control.gui._worker_thread.start_worker` already keeps blocking
work off the GUI thread and outside ``QThread``'s destruction rules.
:class:`TaskController` is the layer above it for work that waits on a network
peer or a device -- the same daemon thread, registry and exit handling, plus
what a bare worker cannot express:

* **Cancellation reaches the backend.** The work receives a
  :class:`CancellationToken`. It polls it (:meth:`~CancellationToken.raise_if_cancelled`,
  :meth:`~CancellationToken.wait`), hands its remaining time to a backend that
  takes a timeout (:meth:`~CancellationToken.remaining`), and registers how to
  let go of what it holds (:meth:`~CancellationToken.on_cancel`): a socket to
  close, a session to stop. Cancelling runs those at once, on the cancelling
  thread, instead of waiting for the backend to give up.
* **Typed outcomes.** :attr:`TaskHandle.result` carries the return value,
  :attr:`TaskHandle.error` the exception object (not its text) and
  :attr:`TaskHandle.progress` whatever the work reports. All three are emitted
  on the GUI thread. Connect them to a method of the owner, or through
  :func:`je_auto_control.gui._weak_call.weak_slot` when it needs arguments:
  the handle is the owner's child, and a lambda or a ``functools.partial``
  that holds the owner would make the handle what keeps the owner alive.
* **Owner death.** The handle is a child of ``owner``, and the controller
  itself only holds the owner weakly. Destroying the owner
  cancels the work; a result that is ready but not delivered yet, or arrives
  later, goes to ``discard`` (close the session nobody will use) and never to
  a slot of the dead widget.
* **No worker touches a widget.** Work that is a widget's method, or closes
  over one, is refused before it starts: read what the work needs from the
  widgets first and pass plain values.
"""
import functools
import threading
import time
import weakref
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from je_auto_control.gui._worker_thread import WorkerHandle, start_worker
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

Work = Callable[["CancellationToken"], object]

_RUNNING = "running"
_DONE = "done"
_FAILED = "failed"
_CANCELLED = "cancelled"
_TIMED_OUT = "timed_out"


class TaskCancelled(AutoControlException):
    """Raised inside the work by :meth:`CancellationToken.raise_if_cancelled`."""


class TaskTimeout(AutoControlException, TimeoutError):
    """Delivered through :attr:`TaskHandle.error` when the work outlived ``timeout_s``."""


class TaskUsageError(AutoControlException, TypeError):
    """The work handed to :meth:`TaskController.submit` could reach a widget."""


class CancellationToken:
    """What the work holds to learn it was cancelled and to release what it took."""

    def __init__(self, timeout_s: Optional[float] = None) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[], object]] = []
        self._deadline = None if timeout_s is None else time.monotonic() + timeout_s
        self._progress: Optional[Callable[[object], None]] = None

    @property
    def cancelled(self) -> bool:
        """Whether the work should stop."""
        return self._event.is_set()

    def cancel(self) -> bool:
        """Mark the work cancelled and run its release callbacks, newest first.

        Returns whether this call was the one that cancelled it. The callbacks
        run on the calling thread -- normally the GUI thread -- so they must be
        quick: close a socket, set an event.
        """
        with self._lock:
            if self._event.is_set():
                return False
            self._event.set()
            callbacks = list(reversed(self._callbacks))
            self._callbacks.clear()
        for callback in callbacks:
            _run_release(callback)
        return True

    def on_cancel(self, callback: Callable[[], object]) -> None:
        """Register how to release something the work holds; runs at once if already cancelled.

        A resource may be released here and again through the task's
        ``discard``, so the callback must tolerate a second call.
        """
        with self._lock:
            if not self._event.is_set():
                self._callbacks.append(callback)
                return
        _run_release(callback)

    def raise_if_cancelled(self) -> None:
        """Raise :class:`TaskCancelled` once the work has been cancelled."""
        if self._event.is_set():
            raise TaskCancelled("the task was cancelled")

    def wait(self, timeout_s: float) -> bool:
        """Sleep up to ``timeout_s``, waking early on cancel; return whether cancelled."""
        return self._event.wait(timeout_s)

    def remaining(self, default: Optional[float] = None) -> Optional[float]:
        """Seconds left before the task's timeout, for a backend that takes one.

        ``default`` is returned when the task has no timeout; a task past its
        deadline gets ``0.0``.
        """
        if self._deadline is None:
            return default
        return max(0.0, self._deadline - time.monotonic())

    def report_progress(self, value: object) -> None:
        """Send ``value`` to :attr:`TaskHandle.progress` (delivered on the GUI thread)."""
        progress = self._progress
        if progress is None or self._event.is_set():
            return
        try:
            progress(value)  # pylint: disable=not-callable  # reason: checked for None above
        except RuntimeError:  # reason: the worker object went away with the application
            pass

    def _seal(self) -> None:
        """Forget the release callbacks: the work is over and owns nothing more."""
        with self._lock:
            self._callbacks.clear()


def _run_release(callback: Callable[[], object]) -> None:
    """Run one release callback; one that fails must not keep the others from running."""
    try:
        callback()
    except Exception as error:  # noqa: BLE001  # reason: logged; the remaining releases must still run
        autocontrol_logger.warning(f"GUI task release callback failed: {error!r}")


class _TaskState:
    """The outcome of one task, shared by its worker thread and the GUI thread."""

    def __init__(self, token: CancellationToken, discard: Optional[Callable[[Any], object]]) -> None:
        self.token = token
        self._discard = discard
        self._lock = threading.Lock()
        self._status = _RUNNING
        self._pending: Optional[Tuple[str, Any]] = None

    @property
    def status(self) -> str:
        """``running``, ``done``, ``failed``, ``cancelled`` or ``timed_out``."""
        with self._lock:
            return self._status

    def finish(self, kind: str, value: Any) -> None:
        """Worker thread: record a result (``done``) or an error (``failed``)."""
        with self._lock:
            keep = self._status == _RUNNING and not self.token.cancelled
            if keep:
                self._status = kind
                self._pending = (kind, value)
            elif self._status == _RUNNING:
                self._status = _CANCELLED
        self.token._seal()  # noqa: SLF001  # reason: the work returned; nothing left to release
        if not keep and kind == _DONE:
            self.discard(value)

    def take(self) -> Optional[Tuple[str, Any]]:
        """GUI thread: the outcome to deliver, once."""
        with self._lock:
            pending, self._pending = self._pending, None
            return pending

    def cancel(self, reason: str = _CANCELLED, *, only_running: bool = False) -> bool:
        """Stop the work, or drop a result nobody collected; return whether anything changed."""
        with self._lock:
            running = self._status == _RUNNING
            pending = self._pending
            if not running and (only_running or pending is None or pending[0] != _DONE):
                return False
            self._pending = None
            self._status = reason
        if pending is not None:
            self.discard(pending[1])
        else:
            self.token.cancel()
        return True

    def discard(self, value: Any) -> None:
        """Hand a result that will not be delivered to the caller's ``discard``."""
        if self._discard is None:
            return
        try:
            self._discard(value)
        except Exception as error:  # noqa: BLE001  # reason: logged; an undelivered result has no caller to tell
            autocontrol_logger.warning(f"GUI task discard failed: {error!r}")


class _TaskWorker(QObject):
    """The ``start_worker`` worker that runs one task's work."""

    finished = Signal(object)
    progressed = Signal(object)

    def __init__(self, work: Work, state: _TaskState) -> None:
        super().__init__()
        self._work = work
        self._state = state

    def run(self) -> None:
        """Call the work with its token and record what came of it."""
        state = self._state
        try:
            value = self._work(state.token)
        except TaskCancelled:
            state.cancel()
        except Exception as error:  # noqa: BLE001  # reason: delivered, typed, through TaskHandle.error
            state.finish(_FAILED, error)
        else:
            state.finish(_DONE, value)
        # The token reports progress through this object's signal; left in
        # place that is a reference cycle through a QObject about to be deleted.
        state.token._progress = None  # noqa: SLF001  # reason: the work is over
        self.finished.emit(None)

    def request_stop(self) -> None:
        """Interpreter exit: stop the work at its next checkpoint."""
        self._state.cancel()


def _nothing(*_args: object) -> None:
    """Stands in for a callback that has been used up."""


class TaskHandle(QObject):
    """One submitted task; its signals are emitted on the GUI thread, while the owner lives.

    ``finished`` is emitted once, after ``result`` / ``error`` or as soon as
    the task is cancelled or times out -- the moment to re-enable a button.
    """

    result = Signal(object)
    error = Signal(object)
    progress = Signal(object)
    finished = Signal()

    def __init__(self, owner: QObject, state: _TaskState) -> None:
        super().__init__(owner)
        self._state = state
        self._worker_handle: Optional[WorkerHandle] = None
        self._announced = False
        self._timer: Optional[QTimer] = None
        self._on_end: Callable[["TaskHandle"], None] = _nothing

    @property
    def state(self) -> str:
        """``running``, ``done``, ``failed``, ``cancelled`` or ``timed_out``."""
        return self._state.status

    @property
    def token(self) -> CancellationToken:
        """The token the work was given."""
        return self._state.token

    def isRunning(self) -> bool:  # noqa: N802  # reason: the QThread spelling the tabs already use
        """Whether the work's thread has not returned yet (it may, after a cancel)."""
        return self._worker_handle is not None and self._worker_handle.isRunning()

    def wait(self, timeout_s: Optional[float] = None) -> bool:
        """Block until the work's thread returns or ``timeout_s`` passes; return whether it did."""
        return self._worker_handle is None or self._worker_handle.wait(timeout_s)

    def cancel(self) -> bool:
        """Stop the work and release what it holds; no ``result`` or ``error`` follows.

        Returns whether there was anything left to cancel.
        """
        changed = self._state.cancel()
        if changed:
            self._announce_finished()
        return changed

    def _start(self, worker: _TaskWorker, timeout_s: Optional[float],
               on_end: Callable[["TaskHandle"], None]) -> None:
        worker.progressed.connect(self._relay_progress)
        if timeout_s is not None:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._on_timeout)
            self._timer.start(max(0, int(timeout_s * 1000)))
        self._on_end = on_end
        self._worker_handle = start_worker(self, worker, on_done=self._deliver,
                                           on_thread_done=self._on_thread_done)

    def _on_thread_done(self) -> None:
        """The work's thread ended and its outcome was delivered: nothing more will be emitted."""
        on_end, self._on_end = self._on_end, _nothing
        on_end(self)
        # Python-side state stays readable; only the Qt object goes, so a tab
        # that polls for hours does not collect one handle per poll. The
        # wrapper must not be left in a reference cycle at this point: PySide
        # corrupted the heap when the collector later freed a cycle that ran
        # through an already-deleted QObject.
        self.deleteLater()

    def _relay_progress(self, value: object) -> None:
        # Reported before the work ended but delivered after: still wanted,
        # unless the task was cancelled in between.
        if self._state.status not in (_CANCELLED, _TIMED_OUT):
            self.progress.emit(value)

    def _on_timeout(self) -> None:
        if self._state.cancel(_TIMED_OUT, only_running=True):
            self.error.emit(TaskTimeout("the task did not finish in time"))
            self._announce_finished()

    def _deliver(self, _value: object = None) -> None:
        if self._timer is not None:
            self._timer.stop()
        pending = self._state.take()
        if pending is not None:
            (self.result if pending[0] == _DONE else self.error).emit(pending[1])
        self._announce_finished()

    def _announce_finished(self) -> None:
        if not self._announced:
            self._announced = True
            self.finished.emit()


def _widgets_reachable_from(work: object, depth: int = 0) -> bool:
    """Whether ``work`` is a widget's method or carries a widget in its closure or bound arguments."""
    carried = [getattr(work, "__self__", None), *_closure_values(work),
               *(getattr(work, "__defaults__", None) or ()),
               *(getattr(work, "__kwdefaults__", None) or {}).values()]
    inner = [getattr(work, "__wrapped__", None)]
    if isinstance(work, functools.partial):
        carried.extend(work.args)
        carried.extend(work.keywords.values())
        inner.append(work.func)
    if any(isinstance(item, QWidget) for item in carried):
        return True
    return depth < 3 and any(_widgets_reachable_from(item, depth + 1) for item in inner if item is not None)


def _closure_values(work: object) -> List[object]:
    """What a function's closure cells hold."""
    values: List[object] = []
    for cell in getattr(work, "__closure__", None) or ():
        try:
            values.append(cell.cell_contents)
        except ValueError:  # reason: an empty cell holds nothing
            continue
    return values


class TaskController:
    """Starts cancellable work for GUI owners and keeps count of what is still running.

    Use from the GUI thread. One shared instance is enough
    (:func:`task_controller`); a tab may also keep its own.
    """

    def __init__(self) -> None:
        # The owner is held weakly: a running task must not keep its tab alive.
        self._active: Dict[TaskHandle, Tuple["weakref.ref[QObject]", Callable[..., None]]] = {}

    def submit(self, work: Work, *, owner: QObject, timeout_s: Optional[float] = None,
               discard: Optional[Callable[[Any], object]] = None) -> TaskHandle:
        """Run ``work(token)`` off the GUI thread for ``owner``; return its handle.

        ``timeout_s`` cancels the work when it passes and reports
        :class:`TaskTimeout`; the work can read what is left of it from
        ``token.remaining()``. ``discard`` receives a result that was produced
        but will not be delivered (the task was cancelled, or ``owner`` was
        destroyed), so a session opened for a tab that is gone can be closed.
        Connect to the handle's signals right after this returns: nothing is
        delivered before control goes back to the event loop.
        """
        if _widgets_reachable_from(work):
            raise TaskUsageError(
                "background work must not hold a widget: read what it needs first and pass plain values")
        state = _TaskState(CancellationToken(timeout_s), discard)
        handle = TaskHandle(owner, state)
        worker = _TaskWorker(work, state)
        state.token._progress = worker.progressed.emit  # noqa: SLF001  # reason: set once, before the thread starts

        def owner_destroyed(*_args: object) -> None:
            self._active.pop(handle, None)
            state.cancel()

        # A plain function, not a slot of the handle: the handle dies with the
        # owner, and this has to run exactly then.
        owner.destroyed.connect(owner_destroyed)
        self._active[handle] = (weakref.ref(owner), owner_destroyed)
        handle._start(worker, timeout_s, self._forget)  # noqa: SLF001  # reason: the handle's second-phase start
        return handle

    def _forget(self, handle: TaskHandle) -> None:
        """GUI thread: ``handle``'s thread ended while its owner is still alive."""
        owner_ref, owner_destroyed = self._active.pop(handle, (None, None))
        owner = owner_ref() if owner_ref is not None else None
        if owner is None:
            return
        try:
            owner.destroyed.disconnect(owner_destroyed)
        except (RuntimeError, TypeError):  # reason: the owner is already going away
            pass

    def cancel_all(self, owner: Optional[QObject] = None) -> int:
        """Cancel every running task, or only ``owner``'s; return how many were cancelled.

        For a tab that is hidden or closed but not destroyed: such a tab
        still owns its tasks.
        """
        handles = [handle for handle, (task_owner, _hook) in self._active.items()
                   if owner is None or task_owner() is owner]
        return sum(1 for handle in handles if handle.cancel())

    def active_count(self) -> int:
        """How many submitted tasks the GUI thread has not yet seen end."""
        return len(self._active)


_DEFAULT: Optional[TaskController] = None


def task_controller() -> TaskController:
    """The controller shared by the tabs, created on first use."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = TaskController()
    return _DEFAULT


__all__ = [
    "CancellationToken", "TaskCancelled", "TaskController", "TaskHandle", "TaskTimeout",
    "TaskUsageError", "task_controller",
]
