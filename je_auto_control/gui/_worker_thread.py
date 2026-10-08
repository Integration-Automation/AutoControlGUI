"""Run a ``QObject`` worker off the GUI thread and deliver its result on the GUI thread.

Four mistakes kept recurring in the tabs that hand work to a thread:

* **The worker lived only in a local variable.** ``moveToThread`` does not
  make the thread own the Python object, so the worker was collected when the
  starting method returned: ``run()`` never executed, the thread stayed up for
  good, and the "one at a time" guard meant the feature never worked again.
* **Results went to a lambda.** A signal emitted on the worker thread runs a
  lambda (or any callable that is not a slot of a GUI-thread ``QObject``) on
  the worker thread, where it set label text and table cells.
* **The thread was a child of the tab.** Closing the tab or the window while
  the work still ran destroyed a running ``QThread`` with it, which aborts the
  process ("QThread: Destroyed while thread is still running").
* **Interpreter exit destroyed a running ``QThread``** -- PySide deletes every
  remaining wrapper at exit -- so a job still inside one long step (an LLM
  request) aborted the process however long exit waited.

:func:`start_worker` therefore runs ``worker.run`` on a daemon
:class:`threading.Thread`: there is no ``QThread`` to destroy, and a job still
running when the interpreter exits simply ends with it. The worker ``QObject``
stays on the GUI thread, so its ``finished`` / ``failed`` signals, emitted from
the worker thread, are queued to a relay the tab owns; the callbacks always run
on the GUI thread and are dropped once the tab is gone. A module-level registry
keeps each worker alive until the GUI thread has seen its thread end.

This module is the thread layer only. Work that waits on a network peer or a
device, and so needs a timeout, cancellation that reaches the backend, typed
errors or progress, goes through :mod:`je_auto_control.gui.task_controller`,
which runs on :func:`start_worker` and shares this registry -- there is one
mechanism, with two levels of use.
"""
import atexit
import threading
import time
import weakref
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal

from je_auto_control.gui._weak_call import WeakCall
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

#: How long interpreter exit waits, in all, for running workers to stop.
_EXIT_GRACE_S = 10.0


class CallWorker(QObject):
    """Runs one callable off the GUI thread and reports the outcome.

    For :func:`start_worker`: ``finished`` carries the return value and
    ``failed`` the error text.
    """

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        """Call the function; emit ``finished`` with its result or ``failed`` with the error."""
        try:
            result = self._fn()
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: surface any backend/transport error to the status line
            self.failed.emit(str(error))
            return
        self.finished.emit(result)


class WorkerHandle:
    """A started worker: running until its thread has returned from ``run()``."""

    def __init__(self, worker: QObject) -> None:
        self.worker = worker
        self._thread: Optional[threading.Thread] = None
        self._owner: Optional["weakref.ref[QObject]"] = None
        self._relay: Optional["weakref.ref[_Relay]"] = None

    def cancel(self) -> None:
        """Ask the worker to stop if it can, and deliver neither its result nor its failure.

        A worker with ``request_stop()`` ends at its next checkpoint; one
        without runs to its end. ``on_thread_done`` still runs when the thread
        ends -- it is the tab's bookkeeping, not an outcome.
        """
        request_stop = getattr(self.worker, "request_stop", None)
        if callable(request_stop):
            request_stop()
        relay = self._relay() if self._relay is not None else None
        if relay is not None:
            relay.drop_outcome()

    def isRunning(self) -> bool:  # noqa: N802  # reason: the QThread spelling its callers use
        """Whether ``run()`` has not returned yet."""
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout_s: Optional[float] = None) -> bool:
        """Block until ``run()`` returns or ``timeout_s`` passes; return whether it did."""
        if self._thread is not None:
            self._thread.join(timeout_s)
        return not self.isRunning()


#: Handles whose thread-end the GUI thread has not processed yet.
_RUNNING: Dict[WorkerHandle, QObject] = {}


class _Reaper(QObject):
    """GUI-thread owner of the registry: releases a worker once its thread ended."""

    ended = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.ended.connect(self._release)

    def _release(self, handle: WorkerHandle) -> None:
        worker = _RUNNING.pop(handle, None)
        if worker is not None:
            worker.deleteLater()


_REAPER: Optional[_Reaper] = None


def _reaper() -> _Reaper:
    """The registry's reaper, created on first use -- on the GUI thread."""
    global _REAPER
    if _REAPER is None:
        _REAPER = _Reaper()
    return _REAPER


class _Relay(QObject):
    """GUI-thread receiver for a worker's outcome, owned by the tab.

    The callbacks are normally methods of the tab this relay is a child of,
    so they are held weakly (:mod:`je_auto_control.gui._weak_call`): held
    strongly, the relay could be the last holder of a parentless tab and
    destroy it from inside its own destructor.
    """

    thread_ended = Signal()
    crashed = Signal(str)

    def __init__(self, parent: QObject,
                 on_done: Callable[[Any], None],
                 on_thread_done: Callable[[], None],
                 on_fail: Optional[Callable[[str], None]]) -> None:
        super().__init__(parent)
        self._on_done = WeakCall(on_done)
        self._on_thread_done = WeakCall(on_thread_done)
        self._on_fail = WeakCall(on_fail)
        self.thread_ended.connect(self.thread_done)
        self.crashed.connect(self.fail)

    def done(self, value: Any) -> None:
        """Forward the worker's result (runs on the GUI thread)."""
        self._on_done(value)

    def drop_outcome(self) -> None:
        """Deliver neither the result nor the failure from now on; the thread's end is still reported."""
        self._on_done = self._on_fail = WeakCall(None)

    def fail(self, message: str) -> None:
        """Forward the worker's failure (runs on the GUI thread)."""
        self._on_fail(message)

    def thread_done(self) -> None:
        """Forward the thread's end (runs on the GUI thread), then go away."""
        self._on_thread_done()
        self.deleteLater()


def _stop_running_workers() -> None:
    """At interpreter exit, ask running workers to stop and give them a moment.

    A worker with a ``request_stop()`` method ends at its next checkpoint;
    the threads share one grace period. One still running after it is a
    daemon thread and ends with the process -- nothing is destroyed under it.
    """
    handles = list(_RUNNING)
    for handle in handles:
        request_stop = getattr(handle.worker, "request_stop", None)
        if callable(request_stop):
            request_stop()
    deadline = time.monotonic() + _EXIT_GRACE_S
    for handle in handles:
        handle.wait(max(0.0, deadline - time.monotonic()))


atexit.register(_stop_running_workers)


def cancel_workers(owner: QObject) -> int:
    """Cancel every worker :func:`start_worker` is still running for ``owner``; return how many.

    What a tab's ``dispose()`` needs: see :meth:`WorkerHandle.cancel`.
    """
    handles = [handle for handle in list(_RUNNING)
               if handle._owner is not None and handle._owner() is owner]  # noqa: SLF001  # reason: own class
    for handle in handles:
        handle.cancel()
    return len(handles)


def running_threads() -> int:
    """How many workers the GUI thread has not yet seen finish."""
    return len(_RUNNING)


def _run(handle: WorkerHandle, relay: Any, reaper: _Reaper) -> None:
    """The worker thread's body: run the worker, then report its end."""
    try:
        handle.worker.run()
    # The worker's own errors go out through its "failed" signal. Anything
    # else goes to on_fail too -- only logging it left a tab showing
    # "Fetching..." for good -- and must not stop the end being reported.
    except Exception as error:  # noqa: BLE001  # reason: reported to on_fail; the end below must still be reported
        autocontrol_logger.error(f"GUI worker {type(handle.worker).__name__} raised: {error!r}")
        _emit_to(relay.crashed, f"{type(error).__name__}: {error}")
    finally:
        _emit_to(relay.thread_ended)
        reaper.ended.emit(handle)


def _emit_to(signal: Any, *args: Any) -> None:
    """Emit on the tab's relay unless the tab, and the relay with it, is gone."""
    try:
        signal.emit(*args)
    except RuntimeError:  # reason: the relay was deleted with its tab
        pass


def start_worker(owner: QObject, worker: QObject, *,
                 on_done: Callable[[Any], None],
                 on_thread_done: Callable[[], None],
                 on_fail: Optional[Callable[[str], None]] = None) -> WorkerHandle:
    """Run ``worker.run`` on a daemon thread on behalf of ``owner``; return its handle.

    Call from the GUI thread. ``worker`` must have a ``finished`` signal and
    may have ``failed``. ``on_done`` / ``on_fail`` / ``on_thread_done`` run on
    the GUI thread, and only while ``owner`` exists: destroying ``owner``
    mid-run drops them and leaves the work to finish on its own. A bound
    method (or a ``functools.partial`` of one) is held weakly, so pass those
    rather than a lambda that closes over ``owner``. The worker is deleted
    once the GUI thread has seen its thread end.
    """
    reaper = _reaper()
    relay = _Relay(owner, on_done, on_thread_done, on_fail)
    worker.finished.connect(relay.done)
    failed = getattr(worker, "failed", None)
    if failed is not None:
        failed.connect(relay.fail)
    handle = WorkerHandle(worker)
    handle._owner, handle._relay = weakref.ref(owner), weakref.ref(relay)  # noqa: SLF001  # reason: set once
    _RUNNING[handle] = worker
    thread = threading.Thread(target=_run, args=(handle, relay, reaper),
                              name=f"gui-worker-{type(worker).__name__}", daemon=True)
    handle._thread = thread  # noqa: SLF001  # reason: set once, before start
    thread.start()
    return handle
