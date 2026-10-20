"""The existing folder toggle binds chunk cancellation to its viewer, engine and original authority."""
from pathlib import Path
import subprocess
import sys
from threading import Event
from types import SimpleNamespace

import pytest

pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from headless.test_webrtc_file_delivery import bridge as bridge
from je_auto_control.gui.remote_desktop import webrtc_panel
from je_auto_control.gui.remote_desktop.folder_sync_io import make_folder_engine
from je_auto_control.utils.rbac import (
    AuthorizationContext, Role, UserStore, authorization_scope, current_authorization,
)
from je_auto_control.utils.remote_desktop.webrtc_files import FileTransferReceiver, FileTransferSender


class Button:
    def setText(self, text):
        self.text = text

    def setChecked(self, checked):
        self.checked = checked


@pytest.mark.parametrize('invalidated', ['viewer', 'engine', 'role', 'authentication', 'connection'])
def test_detached_or_revoked_folder_owner_cannot_begin_a_source_scan(tmp_path, monkeypatch, invalidated):
    watch = tmp_path / 'watch'
    watch.mkdir()
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    viewer = SimpleNamespace(authenticated=True, connection_identity=object())
    owner = SimpleNamespace(viewer=viewer, engine=None)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        engine = make_folder_engine(viewer, str(watch), lambda: owner.viewer, lambda: owner.engine)
    owner.engine = engine
    if invalidated == 'viewer':
        owner.viewer = None
    elif invalidated == 'engine':
        owner.engine = None
    elif invalidated == 'role':
        store.set_role('owner', Role.VIEWER)
    elif invalidated == 'authentication':
        viewer.authenticated = False
    else:
        viewer.connection_identity = object()
    scans = []

    def forbidden(_stop):
        scans.append(True)
        pytest.fail('invalidated work read the source')

    monkeypatch.setattr(engine, '_scan', forbidden)
    engine.start()
    worker = engine._thread
    try:
        if worker is not None:
            worker.join(5)
        assert not engine.is_running() and engine.stop_requested
        assert not engine.wait_until_ready(0) and scans == []
    finally:
        engine.stop()


@pytest.mark.parametrize('invalidated', ['stop', 'viewer', 'engine', 'role', 'authentication', 'connection'])
@pytest.mark.parametrize('via_gui', [False, True])
def test_mid_file_stop_or_replacement_aborts_without_committing_partial_bytes(
        bridge, tmp_path, monkeypatch, invalidated, via_gui):
    _active, failures = bridge
    watch = tmp_path / 'watch'
    watch.mkdir()
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    target = tmp_path / 'inbox' / 'payload.bin'
    target.write_bytes(b'previous target')
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    finished = Event()
    writes = []
    contexts = []
    completed = []

    class Channel:
        def send(self, message):
            receiver.handle_message(message, on_done=completed.append)

    class Viewer:
        authenticated = True
        connection_identity = object()

        def set_file_receipt_callback(self, callback):
            self.received_callback = callback

        def send_file(self, path, remote_name=None, on_progress=None, *, cancelled=None, require_commit=False):
            assert require_commit
            # This cancellation-only double stops before commit; native-pair tests cover receipt negotiation.
            contexts.append(current_authorization().user_id)

            def accepted(sent, _total):
                writes.append(sent)
                if invalidated == 'stop':
                    engine.stop()
                elif invalidated == 'viewer':
                    owner._viewer = None
                elif invalidated == 'engine':
                    owner._sync_engine = None
                elif invalidated == 'role':
                    store.set_role('owner', Role.VIEWER)
                elif invalidated == 'authentication':
                    self.authenticated = False
                else:
                    self.connection_identity = object()

            try:
                FileTransferSender(Channel()).send(path, remote_name=remote_name, chunk_size=4,
                                                    on_progress=accepted, cancelled=cancelled)
            finally:
                finished.set()

    viewer = Viewer()
    owner = SimpleNamespace(_viewer=viewer, _sync_engine=None, _sync_dir_edit=SimpleNamespace(text=lambda: str(watch)),
                            _sync_btn=Button(), _require_viewer=lambda: viewer)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    factory = make_folder_engine

    def fast_factory(*args):
        result = factory(*args)
        result._interval = .001
        return result

    monkeypatch.setattr(webrtc_panel, 'make_folder_engine', fast_factory)
    with authorization_scope(context):
        if via_gui:
            webrtc_panel._WebRTCViewerPanel._on_toggle_sync(owner, True)
            engine = owner._sync_engine
        else:
            engine = fast_factory(viewer, str(watch), lambda: owner._viewer, lambda: owner._sync_engine)
            owner._sync_engine = engine
            engine.start()
    worker = engine._thread
    try:
        assert engine.wait_until_ready()
        (watch / 'payload.bin').write_bytes(b'abcdefgh')
        assert finished.wait(5)
        worker.join(5)
        assert not engine.is_running() and engine.stop_requested and not engine.wait_until_ready(0)
        assert writes == [4] and contexts == ['owner']
        assert target.read_bytes() == b'previous target' and completed == []
        assert sorted(path.name for path in target.parent.iterdir()) == ['payload.bin']
        assert failures == []
    finally:
        engine.stop()


def test_owner_replaced_after_scan_can_stop_without_reentering_a_nonrecursive_lock(tmp_path):
    program = """
from pathlib import Path
from types import SimpleNamespace
from je_auto_control.gui.remote_desktop.folder_sync_io import make_folder_engine
import sys
viewer = SimpleNamespace(authenticated=True, connection_identity=object())
owner = SimpleNamespace(viewer=viewer, engine=None)
engine = make_folder_engine(viewer, sys.argv[1], lambda: owner.viewer, lambda: owner.engine)
owner.engine = engine
scan = engine._scan
def replaced(stop):
    result = scan(stop)
    owner.viewer = None
    return result
engine._scan = replaced
engine.start()
worker = engine._thread
if worker is not None:
    worker.join(1)
sys.exit(1 if worker is not None and worker.is_alive() else 0)
"""
    result = subprocess.run([sys.executable, '-c', program, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True,
                            encoding='utf-8', timeout=20, check=False)
    assert result.returncode == 0, result.stderr or 'owner cancellation deadlocked the polling lifecycle lock'
