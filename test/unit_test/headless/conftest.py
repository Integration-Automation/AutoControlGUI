"""Shared teardown for the headless suite."""
import sys

import pytest


def _live_qt_application():
    """The running QApplication, or None.

    Looks in ``sys.modules`` rather than importing PySide6: most of this suite
    is Qt-free, and importing Qt to ask whether Qt is in use would load it into
    every one of those runs.
    """
    widgets = sys.modules.get("PySide6.QtWidgets")
    if widgets is None:
        return None
    return widgets.QApplication.instance()


@pytest.fixture(autouse=True)
def flush_qt_deferred_deletes():
    """Run Qt's queued ``deleteLater()`` work at the end of every test.

    ``deleteLater()`` does nothing until an event loop runs, and almost no GUI
    test module here runs one. Left queued, a widget — and any helper thread or
    timer it started at construction — survives until some *later* test pumps
    events, and is then destroyed inside that unrelated test.

    That is not hypothetical: seven ``AdminConsoleTab``s queued by
    ``test_admin_console_thumbnails_gui.py`` were destroyed inside the nested
    modal ``exec()`` of ``test_usb_acl_prompt.py``, killing the interpreter with
    rc 3221226505 (0xC0000409, a ``__fastfail``). There was no traceback,
    faulthandler could not see it, and the ~500 tests after it never ran.

    Flushing here makes each test clean up after itself, so no test module has
    to remember. Being autouse, this is set up before any test-local fixture
    and therefore torn down *after* it — the module's own ``deleteLater()``
    calls have already been made by the time this runs.
    """
    yield
    app = _live_qt_application()
    if app is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
