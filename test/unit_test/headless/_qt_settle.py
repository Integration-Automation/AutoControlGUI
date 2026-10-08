"""Wait for a panel's off-thread work to answer on the GUI thread.

Connects, device runs and OCR left the GUI thread (plan F3), so a test that
calls the slot has to pump the event loop before it reads the outcome. It must
also not *end* before the outcome is delivered: a warning delivered during
another test's teardown, with ``QMessageBox`` no longer patched, opens a real
modal box and the run hangs.
"""
import time

from PySide6.QtWidgets import QApplication


def settle(owner, attribute: str = "_connect_task", timeout: float = 10.0) -> bool:
    """Pump events until ``owner.<attribute>`` is None again; return whether it is."""
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while getattr(owner, attribute) is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return getattr(owner, attribute) is None


def pump_until(predicate, timeout: float = 10.0) -> bool:
    """Pump events until ``predicate()`` is true or ``timeout`` passes; return whether it is."""
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


def settle_op(op, timeout: float = 10.0) -> bool:
    """Pump events until a ``SlowOp`` is idle or a ``StopQueue`` has drained; return whether it has.

    Stops that join a thread left the GUI thread, so a test that calls Stop
    (or a Start that first stops) pumps here before it reads the outcome.
    """
    def idle() -> bool:
        return not getattr(op, "busy", False) and not getattr(op, "pending", 0)

    return pump_until(idle, timeout)
