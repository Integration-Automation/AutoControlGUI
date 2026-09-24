"""Run a ``QObject`` worker on a ``QThread`` and deliver its result on the GUI thread.

Two mistakes kept recurring in the tabs that hand work to a thread:

* **The worker lived only in a local variable.** ``moveToThread`` does not
  make the thread own the Python object, so the worker was collected when the
  starting method returned: ``run()`` never executed, the ``QThread`` stayed
  up for good, and the "one at a time" guard meant the feature never worked
  again. Destroying the tab with that thread alive then aborted the process
  ("QThread: Destroyed while thread is still running").
* **Results went to a lambda.** A signal emitted on the worker thread runs a
  lambda (or any callable that is not a slot of a GUI-thread ``QObject``) on
  the worker thread, where it set label text and table cells.

:func:`start_worker` keeps the worker alive on a relay that lives on the GUI
thread and forwards ``finished`` / ``failed`` through the relay's slots, so the
callbacks always run on the GUI thread whatever they are.
"""
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread


class _Relay(QObject):
    """GUI-thread receiver for a worker's outcome; also keeps the worker alive."""

    def __init__(self, parent: QObject, worker: QObject,
                 on_done: Callable[[Any], None],
                 on_fail: Optional[Callable[[str], None]]) -> None:
        super().__init__(parent)
        self.worker = worker
        self._on_done = on_done
        self._on_fail = on_fail

    def done(self, value: Any) -> None:
        """Forward the worker's result (runs on the GUI thread)."""
        self._on_done(value)

    def fail(self, message: str) -> None:
        """Forward the worker's failure (runs on the GUI thread)."""
        if self._on_fail is not None:
            self._on_fail(message)


def start_worker(owner: QObject, worker: QObject, *,
                 on_done: Callable[[Any], None],
                 on_thread_done: Callable[[], None],
                 on_fail: Optional[Callable[[str], None]] = None) -> QThread:
    """Start ``worker.run`` on a new thread parented to ``owner``; return the thread.

    ``worker`` must have a ``finished`` signal and may have ``failed``.
    ``on_done`` / ``on_fail`` run on the GUI thread; ``on_thread_done`` runs
    when the thread has stopped. The thread, the worker and the relay are all
    deleted once the thread finishes.
    """
    thread = QThread(owner)
    relay = _Relay(owner, worker, on_done, on_fail)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(relay.done)
    worker.finished.connect(thread.quit)
    failed = getattr(worker, "failed", None)
    if failed is not None:
        failed.connect(relay.fail)
        failed.connect(thread.quit)
    thread.finished.connect(on_thread_done)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(relay.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
