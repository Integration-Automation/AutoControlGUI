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


# Backend calls that move the pointer or type on the real desktop.
_INPUT_CALLS = frozenset({
    "mouse_event", "set_position", "press_mouse", "release_mouse", "click_mouse", "scroll",
    "send_mouse_event_to_window", "press_key", "release_key", "press_unicode",
    "release_unicode", "type_unicode_unit", "send_key_event_to_window",
})


class _RecordingBackend:
    """The platform backend with every input call recorded instead of performed."""

    def __init__(self, real, calls):
        self._real = real
        self._calls = calls

    def __getattr__(self, name):
        attribute = getattr(self._real, name)
        if name not in _INPUT_CALLS or not callable(attribute):
            return attribute

        def record(*args, **kwargs):
            self._calls.append((name, args))

        return record


@pytest.fixture(autouse=True)
def refuse_real_input(monkeypatch):
    """Fail a test whose input reaches the real mouse or keyboard backend.

    A test that faked ``press_mouse`` but not ``set_mouse_position`` moved
    the real cursor on every run -- on a desktop where another program may be
    typing. Every test sees the backends through a recorder instead: a call
    that reaches it does nothing, and the test fails naming it, so the fake
    that is missing gets added. Tests that install their own backend fake
    replace the recorder and are unaffected.
    """
    wrappers = sys.modules.get("je_auto_control.wrapper.platform_wrapper")
    if wrappers is None:
        yield
        return
    from je_auto_control.wrapper import auto_control_keyboard, auto_control_mouse
    calls = []
    mouse = _RecordingBackend(wrappers.mouse, calls)
    keyboard = _RecordingBackend(wrappers.keyboard, calls)
    for module, name, guard in ((wrappers, "mouse", mouse), (wrappers, "keyboard", keyboard),
                                (auto_control_mouse, "mouse", mouse),
                                (auto_control_keyboard, "keyboard", keyboard)):
        monkeypatch.setattr(module, name, guard)
    yield
    if calls:
        pytest.fail(f"the test reached the real input backend: {calls[:5]}", pytrace=False)
