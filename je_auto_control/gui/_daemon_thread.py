"""A ``QThread`` stand-in whose ``run()`` executes on a daemon Python thread.

Destroying a running ``QThread`` aborts the process ("QThread: Destroyed while
thread is still running"): closing a panel mid-transfer took its child thread
with it, and interpreter exit -- PySide deletes every remaining wrapper --
aborted on any thread still inside a long signaling poll. :class:`DaemonThread`
keeps the part of the ``QThread`` API the remote-desktop workers use
(``start``, ``run``, ``isRunning``, ``wait``, ``requestInterruption``,
``isInterruptionRequested``, the ``started`` / ``finished`` signals) but runs
``run()`` on a daemon :class:`threading.Thread`. Deleting the object never
touches the thread, and a thread still blocked at exit ends with the process.

The object itself stays on the GUI thread, so signals ``run()`` emits reach
GUI-thread receivers through queued connections, exactly as a ``QThread``
subclass's did.
"""
import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


class DaemonThread(QObject):
    """Subclass and override :meth:`run`, as with ``QThread``."""

    started = Signal()
    finished = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._interruption = threading.Event()

    def run(self) -> None:
        """The work; runs on the daemon thread. Override it."""

    def start(self) -> None:
        """Run :meth:`run` on a new daemon thread (no-op while one is running)."""
        if self.isRunning():
            return
        self._interruption.clear()
        # The bound method keeps this wrapper alive until the thread ends.
        self._thread = threading.Thread(target=self._main, daemon=True,
                                        name=type(self).__name__)
        self._thread.start()

    def _main(self) -> None:
        try:
            self.started.emit()
            self.run()
        # run() is subclass code; a failure must end the thread quietly and
        # still report finished, as a QThread's end does.
        except Exception as error:  # noqa: BLE001  # reason: logged; finished is still emitted below
            autocontrol_logger.error(f"{type(self).__name__} failed: {error!r}")
        finally:
            try:
                self.finished.emit()
            except RuntimeError:  # reason: the object was deleted while the thread ran
                pass

    def isRunning(self) -> bool:  # noqa: N802  # reason: the QThread spelling its callers use
        """Whether :meth:`run` has not returned yet."""
        return self._thread is not None and self._thread.is_alive()

    def wait(self, msecs: Optional[int] = None) -> bool:
        """Block until :meth:`run` returns or ``msecs`` pass; return whether it did."""
        if self._thread is not None:
            self._thread.join(None if msecs is None else msecs / 1000.0)
        return not self.isRunning()

    def requestInterruption(self) -> None:  # noqa: N802  # reason: QThread API
        """Ask :meth:`run` to stop at its next :meth:`isInterruptionRequested` check."""
        self._interruption.set()

    def isInterruptionRequested(self) -> bool:  # noqa: N802  # reason: QThread API
        """Whether :meth:`requestInterruption` was called since :meth:`start`."""
        return self._interruption.is_set()
