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
