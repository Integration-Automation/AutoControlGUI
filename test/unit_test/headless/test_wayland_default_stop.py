"""Stopping default native control must cancel an unanswered handshake without waiting on its cache lock."""
import threading

import pytest

from je_auto_control.linux_wayland import libei
from je_auto_control.linux_wayland.permission import WaylandPermissionRequired


@pytest.mark.parametrize('operation', ['stop', 'reset'])
def test_pending_default_handshake_is_cancelled_without_publishing_stale_grant(monkeypatch, operation):
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    failures = []

    class Pending:
        def connect(self):
            entered.set()
            assert release.wait(3)

        def disconnect(self):
            release.set()

    pending = Pending()
    monkeypatch.setattr(libei, '_DEFAULT_BACKEND', None)
    monkeypatch.setattr(libei, '_PROBE_FAILED', False)
    monkeypatch.setattr(libei, '_PERMISSION_ERROR', None)
    monkeypatch.setattr(libei, '_new_default_backend', lambda: pending)

    def connect():
        try:
            libei.connected_backend()
        except WaylandPermissionRequired as failure:
            failures.append(failure)

    def stop():
        (libei.stop_input_control if operation == 'stop' else libei.reset_default_backend)()
        stopped.set()

    connector = threading.Thread(target=connect)
    connector.start()
    assert entered.wait(2)
    stopper = threading.Thread(target=stop)
    stopper.start()
    try:
        assert stopped.wait(0.25), 'stop/reset was blocked by the unanswered authorization'
    finally:
        release.set()
        connector.join(3)
        stopper.join(3)
    assert not connector.is_alive() and not stopper.is_alive()
    assert libei._DEFAULT_BACKEND is None
    assert len(failures) == 1
    if operation == 'stop':
        assert libei.input_permission_status()[0] == 'needs_permission'
    else:
        assert libei.input_permission_status() is None
