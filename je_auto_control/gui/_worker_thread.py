"""Run a ``QObject`` worker on a ``QThread`` and deliver its result on the GUI thread.

Three mistakes kept recurring in the tabs that hand work to a thread:

* **The worker lived only in a local variable.** ``moveToThread`` does not
  make the thread own the Python object, so the worker was collected when the
  starting method returned: ``run()`` never executed, the ``QThread`` stayed
  up for good, and the "one at a time" guard meant the feature never worked
  again.
* **Results went to a lambda.** A signal emitted on the worker thread runs a
  lambda (or any callable that is not a slot of a GUI-thread ``QObject``) on
  the worker thread, where it set label text and table cells.
* **The thread was a child of the tab.** Closing the tab or the window while
  the work still ran destroyed the running ``QThread`` with it, which aborts
  the process ("QThread: Destroyed while thread is still running").

:func:`start_worker` keeps the thread and the worker in a module-level registry
until the thread has finished, and forwards the outcome through a relay owned
by the tab, so the callbacks always run on the GUI thread and are simply
dropped once the tab is gone.
"""
import atexit
import time
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import QObject, QThread

#: Threads still running (or not yet deleted), each with its worker, so that
#: neither is destroyed with the tab that started it.
_RUNNING: Dict[QThread, QObject] = {}


#: How long interpreter exit waits, in all, for worker threads to wind down.
_EXIT_GRACE_S = 10.0


def _stop_running_threads() -> None:
    """At interpreter exit, let every worker thread finish before Qt destroys it.

    Destroying a running ``QThread`` aborts the process, and PySide destroys
    every remaining wrapper at exit. A worker's ``finished`` only *queues*
    ``quit`` on the GUI thread, which no longer runs an event loop by then, so
    the thread's own loop is told to quit directly, and the threads share one
    grace period. A worker with a ``request_stop()`` method is asked to stop
    first, so a long ``run()`` ends at its next checkpoint.
    """
    for worker in list(_RUNNING.values()):
        request_stop = getattr(worker, "request_stop", None)
        if callable(request_stop):
            request_stop()
    deadline = time.monotonic() + _EXIT_GRACE_S
    # Every thread here is still alive: ``destroyed`` removes it first.
    for thread in list(_RUNNING):
        thread.quit()
        remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
        thread.wait(remaining_ms)


atexit.register(_stop_running_threads)


class _Relay(QObject):
    """GUI-thread receiver for a worker's outcome, owned by the tab."""

    def __init__(self, parent: QObject,
                 on_done: Callable[[Any], None],
                 on_thread_done: Callable[[], None],
                 on_fail: Optional[Callable[[str], None]]) -> None:
        super().__init__(parent)
        self._on_done = on_done
        self._on_thread_done = on_thread_done
        self._on_fail = on_fail

    def done(self, value: Any) -> None:
        """Forward the worker's result (runs on the GUI thread)."""
        self._on_done(value)

    def fail(self, message: str) -> None:
        """Forward the worker's failure (runs on the GUI thread)."""
        if self._on_fail is not None:
            self._on_fail(message)

    def thread_done(self) -> None:
        """Forward the thread's end (runs on the GUI thread)."""
        self._on_thread_done()


def running_threads() -> int:
    """How many worker threads have not been deleted yet."""
    return len(_RUNNING)


def start_worker(owner: QObject, worker: QObject, *,
                 on_done: Callable[[Any], None],
                 on_thread_done: Callable[[], None],
                 on_fail: Optional[Callable[[str], None]] = None) -> QThread:
    """Start ``worker.run`` on a new thread on behalf of ``owner``; return the thread.

    ``worker`` must have a ``finished`` signal and may have ``failed``.
    ``on_done`` / ``on_fail`` / ``on_thread_done`` run on the GUI thread, and
    only while ``owner`` exists: destroying ``owner`` mid-run drops them and
    leaves the thread to finish on its own. The thread, the worker and the
    relay are all deleted once the thread finishes.
    """
    thread = QThread()
    relay = _Relay(owner, on_done, on_thread_done, on_fail)
    _RUNNING[thread] = worker
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(relay.done)
    worker.finished.connect(thread.quit)
    failed = getattr(worker, "failed", None)
    if failed is not None:
        failed.connect(relay.fail)
        failed.connect(thread.quit)
    thread.finished.connect(relay.thread_done)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(relay.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.destroyed.connect(lambda *_args: _RUNNING.pop(thread, None))
    thread.start()
    return thread
