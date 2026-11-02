"""Wait for a panel's off-thread work to answer on the GUI thread.

Connects, device runs and OCR left the GUI thread (plan F3), so a test that
calls the slot has to pump the event loop before it reads the outcome. It must
also not *end* before the outcome is delivered: a warning delivered during
another test's teardown, with ``QMessageBox`` no longer patched, opens a real
modal box and the run hangs.
"""
import contextlib
import time

from PySide6.QtWidgets import QApplication
from shiboken6 import Shiboken


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


@contextlib.contextmanager
def deleting(*classes):
    """Schedule for deletion, on exit, every instance of ``classes`` made inside the block.

    A panel a test builds without a parent and never deletes does not go away
    with the test: its slots are lambdas that close over it, Qt holds those, and
    the collector cannot see through Qt. It stays a top-level widget for the
    rest of the run -- with its timers, its listeners and the popup container
    of every ``QComboBox`` on it. Wrap the test in this (an autouse fixture
    does it for a whole module) so each test deletes what it built; the
    autouse flush in ``conftest.py`` then runs the deferred deletes.

    The instances are recorded as they are made. They are never looked up
    through ``QApplication.topLevelWidgets()``, which is unsafe on Python
    3.10 / 3.11 (see ``test_usb_acl_prompt._open_prompt``).
    """
    made = []
    restore = []

    def recording(original):
        def __init__(self, *args, **kwargs):
            original(self, *args, **kwargs)
            made.append(self)
        return __init__

    for cls in classes:
        restore.append((cls, cls.__dict__.get("__init__")))
        cls.__init__ = recording(cls.__init__)
    try:
        yield made
    finally:
        for cls, own in restore:
            if own is None:
                del cls.__init__            # it was inherited
            else:
                cls.__init__ = own
        for widget in made:
            if Shiboken.isValid(widget) and widget.parent() is None:
                widget.deleteLater()
        del made[:]
