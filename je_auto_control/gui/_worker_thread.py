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
"""
import atexit
import threading
import time
import weakref
from types import MethodType
from typing import Any, Callable, Dict, Optional
import uuid

from PySide6.QtCore import QObject, Signal
from shiboken6 import isValid  # pylint: disable=no-name-in-module  # reason: native Qt wrapper validity

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.gui._task_state import CancellationToken, TaskCancelled
from je_auto_control.utils.executor.cancellation import _task_scope
from je_auto_control.utils.executor.input_owner import InputOwner, _input_scope
from je_auto_control.utils.executor.request_context import RequestBinding

_INPUT_OWNERS: weakref.WeakKeyDictionary[QObject, InputOwner] = weakref.WeakKeyDictionary()


def _owner_inputs(owner: QObject) -> InputOwner:
    inputs = _INPUT_OWNERS.get(owner)
    if inputs is None:
        inputs = InputOwner()
        _INPUT_OWNERS[owner] = inputs
        owner.destroyed.connect(inputs.close)
    return inputs

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
        self.token = CancellationToken(uuid.uuid4().hex, 300, lambda _value: None)
        self._inputs: InputOwner | None = None
        self._binding = RequestBinding.capture()

    def bind_inputs(self, inputs: InputOwner) -> None:
        """Bind headless input ownership before the native worker starts."""
        self._inputs = inputs

    def request_stop(self) -> None:
        """Revoke nested actions and waits without blocking the GUI thread."""
        self.token.cancel()

    def run(self) -> None:
        """Call the function; emit ``finished`` with its result or ``failed`` with the error."""
        try:
            with _task_scope(self.token), _input_scope(self._inputs, self.token.run_id):
                self.token.checkpoint()
                result = self._binding.run(self._fn)
                self.token.checkpoint()
        except TaskCancelled:
            return
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: surface any backend/transport error to the status line
            if self._inputs is not None:
                self._inputs.request_cleanup(self.token.run_id)
            self.failed.emit(str(error))
            return
        finally:
            if self.token.event.is_set() and self._inputs is not None:
                self._inputs.request_cleanup(self.token.run_id)
        self.finished.emit(result)


class WorkerHandle:
    """A started worker: running until its thread has returned from ``run()``."""

    def __init__(self, worker: QObject) -> None:
        self.worker = worker
        self._thread: Optional[threading.Thread] = None

    def isRunning(self) -> bool:  # pylint: disable=invalid-name  # reason: legacy QThread spelling
        """Whether ``run()`` has not returned yet."""
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout_s: Optional[float] = None) -> bool:
        """Block until ``run()`` returns or ``timeout_s`` passes; return whether it did."""
        if self._thread is not None:
            self._thread.join(timeout_s)
        return not self.isRunning()


#: Handles whose thread-end the GUI thread has not processed yet.
_RUNNING: Dict[WorkerHandle, QObject] = {}
_RUN_OWNERS: dict[WorkerHandle, weakref.ReferenceType[QObject]] = {}


class _Reaper(QObject):
    """GUI-thread owner of the registry: releases a worker once its thread ended."""

    ended = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.ended.connect(self._release)

    def _release(self, handle: WorkerHandle) -> None:
        worker = _RUNNING.pop(handle, None)
        owner = _RUN_OWNERS.pop(handle, lambda: None)()
        if worker is not None:
            stop = getattr(worker, 'request_stop', None)
            if owner is not None and isValid(owner) and callable(stop):
                owner.destroyed.disconnect(stop)
            worker.deleteLater()


_REAPER: Optional[_Reaper] = None


def _reaper() -> _Reaper:
    """The registry's reaper, created on first use -- on the GUI thread."""
    global _REAPER  # pylint: disable=global-statement  # reason: one reaper created on the GUI thread
    if _REAPER is None:
        _REAPER = _Reaper()
    return _REAPER


class _Relay(QObject):
    """GUI-thread receiver for a worker's outcome, owned by the tab."""

    thread_ended = Signal()
    crashed = Signal(str)

    def __init__(self, parent: QObject,
                 on_done: Callable[[Any], None],
                 on_thread_done: Callable[[], None],
                 on_fail: Optional[Callable[[str], None]]) -> None:
        super().__init__(parent)
        self._on_done = _owner_callback(parent, on_done)
        self._on_thread_done = _owner_callback(parent, on_thread_done)
        self._on_fail = _owner_callback(parent, on_fail) if on_fail is not None else None
        self.thread_ended.connect(self.thread_done)
        self.crashed.connect(self.fail)

    def done(self, value: Any) -> None:
        """Forward the worker's result (runs on the GUI thread)."""
        self._on_done(value)

    def fail(self, message: str) -> None:
        """Forward the worker's failure (runs on the GUI thread)."""
        if self._on_fail is not None:
            self._on_fail(message)

    def thread_done(self) -> None:
        """Forward the thread's end (runs on the GUI thread), then go away."""
        self._on_thread_done()
        self.deleteLater()


def _owner_callback(owner: QObject, callback: Callable[..., Any]) -> Callable[..., Any]:
    """Avoid retaining the Qt parent through a relay's bound Python callbacks."""
    if not isinstance(callback, MethodType) or callback.__self__ is not owner:
        return callback
    reference = weakref.WeakMethod(callback)

    def invoke(*args: Any) -> Any:
        method = reference()
        return method(*args) if method is not None else None
    return invoke


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


def running_threads() -> int:
    """How many workers the GUI thread has not yet seen finish."""
    return len(_RUNNING)


def cancel_workers(owner: QObject) -> None:
    """Cancel work belonging to the selected panel or its children; global services stay explicit."""
    related = {owner, *owner.findChildren(QObject)}
    for handle, reference in tuple(_RUN_OWNERS.items()):
        if reference() in related:
            stop = getattr(handle.worker, 'request_stop', None)
            if callable(stop):
                stop()
    for widget in related:
        inputs = _INPUT_OWNERS.get(widget)
        if inputs is not None:
            inputs.request_cleanup()


def _run(handle: WorkerHandle, relay: Any, reaper: _Reaper) -> None:
    """The worker thread's body: run the worker, then report its end."""
    try:
        handle.worker.run()
    # The worker's own errors go out through its "failed" signal. Anything
    # else goes to on_fail too -- only logging it left a tab showing
    # "Fetching..." for good -- and must not stop the end being reported.
    except Exception as error:  # pylint: disable=broad-exception-caught  # reason: reports crashes and always reaps the worker
        autocontrol_logger.error('GUI worker %s raised: %r', type(handle.worker).__name__, error)
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
    mid-run drops them and leaves the work to finish on its own. The worker is
    deleted once the GUI thread has seen its thread end.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: lifecycle check is needed only when explicitly starting GUI work
    from je_auto_control.gui.tab_registry import _require_gui_thread
    _require_gui_thread()
    if type(worker) is CallWorker:  # pylint: disable=unidiomatic-typecheck  # reason: subclasses manage their own scope
        worker.bind_inputs(_owner_inputs(owner))
    stop = getattr(worker, 'request_stop', None)
    if callable(stop):
        owner.destroyed.connect(stop)
    reaper = _reaper()
    relay = _Relay(owner, on_done, on_thread_done, on_fail)
    worker.finished.connect(relay.done)
    failed = getattr(worker, "failed", None)
    if failed is not None:
        failed.connect(relay.fail)
    handle = WorkerHandle(worker)
    _RUNNING[handle] = worker
    _RUN_OWNERS[handle] = weakref.ref(owner)
    thread = threading.Thread(target=_run, args=(handle, relay, reaper),
                              name=f"gui-worker-{type(worker).__name__}", daemon=True)
    handle._thread = thread  # pylint: disable=protected-access  # reason: same-module initialization before start
    thread.start()
    return handle
