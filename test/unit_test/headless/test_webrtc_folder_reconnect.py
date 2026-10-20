"""GUI reconnect keeps failed/offline edits for the same authenticated peer and local owner."""
from pathlib import Path
from hashlib import sha256
from threading import Event
from types import SimpleNamespace

import pytest

pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from headless._webrtc_doubles import FakePeerConnection
from headless.test_folder_sync_content import loop
from headless.test_webrtc_file_commit import bounded_waits as bounded_waits, native_pair as native_pair
from headless.test_webrtc_file_delivery import bridge as bridge
from je_auto_control.gui.remote_desktop import webrtc_panel
from je_auto_control.gui.remote_desktop import folder_sync_controls
from je_auto_control.utils.rbac import AuthorizationContext, Role, UserStore, authorization_scope
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.remote_desktop.webrtc_viewer import WebRTCDesktopViewer

_REAL_START = FolderSyncEngine.start


@pytest.fixture
def folder_panel(native_pair, tmp_path, monkeypatch):
    watch = tmp_path / 'watch'
    watch.mkdir()
    (watch / 'existing.bin').write_bytes(b'initial baseline')
    button = SimpleNamespace(setChecked=lambda _value: None, setText=lambda _text: None)
    owner = SimpleNamespace(_viewer=native_pair.viewer, _sync_engine=None, _offer_worker=None, _answer_worker=None,
                            _recorder=None, _sync_dir_edit=SimpleNamespace(text=lambda: str(watch)), _sync_btn=button,
                            _stop_stats_polling=lambda: None, watch=watch, warnings=[])
    owner._require_viewer = lambda: owner._viewer
    native_pair.viewer._host_fingerprint = 'a' * 64
    monkeypatch.setattr(FolderSyncEngine, 'start', lambda _engine: None)
    monkeypatch.setattr(folder_sync_controls.QMessageBox, 'warning',
                        lambda _owner, _title, message: owner.warnings.append(message))
    yield owner, native_pair
    if owner._sync_engine is not None:
        owner._sync_engine.stop()


def toggle(owner, checked=True):
    webrtc_panel._WebRTCViewerPanel._on_toggle_sync(owner, checked)
    return owner._sync_engine


def disconnect(owner):
    webrtc_panel._WebRTCViewerPanel._stop_viewer_if_any(owner)


def reconnect(owner, pair, fingerprint='a' * 64):
    async def setup():
        viewer = WebRTCDesktopViewer(token='controlled')
        viewer._pc, viewer._authenticated, viewer._host_fingerprint = FakePeerConnection(), True, fingerprint
        outgoing, incoming = type(pair.outgoing)('outbound', 'open'), type(pair.incoming)('inbound', 'open')
        outgoing.peer, incoming.peer = incoming, outgoing
        viewer._wire_files_channel(outgoing)
        pair.host._wire_files_channel(incoming)
        return viewer, outgoing, incoming
    viewer, outgoing, incoming = pair.bridge.submit(setup()).result(5)
    pair.viewer, pair.outgoing, pair.incoming = viewer, outgoing, incoming
    owner._viewer = viewer
    pair.drop_data = False


@pytest.mark.parametrize('failed_before_disconnect', [False, True])
def test_existing_gui_stop_and_restart_retries_failed_and_offline_bytes(folder_panel, failed_before_disconnect):
    owner, pair = folder_panel
    engine = toggle(owner)
    loop(engine)
    if failed_before_disconnect:
        pair.drop_data = True
        loop(engine, lambda: (owner.watch / 'pending.bin').write_bytes(b'previously unconfirmed'), lambda: None)
        assert not (pair.receiver / 'pending.bin').exists()
    disconnect(owner)
    assert owner._viewer is None and owner._sync_engine is None and engine.stop_requested
    (owner.watch / 'existing.bin').write_bytes(b'offline change')
    (owner.watch / 'offline.bin').write_bytes(b'created while disconnected')
    reconnect(owner, pair)
    replacement = toggle(owner)
    assert replacement is not engine
    loop(replacement)
    assert (pair.receiver / 'existing.bin').is_file(), 'reconnect silently baselined an offline change'
    assert (pair.receiver / 'existing.bin').read_bytes() == b'offline change'
    assert (pair.receiver / 'offline.bin').read_bytes() == b'created while disconnected'
    if failed_before_disconnect:
        assert (pair.receiver / 'pending.bin').read_bytes() == b'previously unconfirmed'
    assert sorted(Path(name).name for name in replacement._content.snapshot) == sorted(
        path.name for path in owner.watch.iterdir())


@pytest.mark.parametrize('changed', ['host', 'missing-fingerprint', 'root', 'user', 'store', 'trusted-role'])
def test_another_peer_root_or_principal_does_not_inherit_the_previous_baseline(folder_panel, tmp_path, changed):
    owner, pair = folder_panel
    context = AuthorizationContext('first', Role.OPERATOR)
    store = UserStore(tmp_path / 'users.json')
    if changed == 'store':
        store.add_user(user_id='first', display_name='First', role=Role.OPERATOR)
        context = AuthorizationContext('first', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        loop(toggle(owner))
    disconnect(owner)
    (owner.watch / 'pending.bin').write_bytes(b'old pending data')
    fingerprint = 'b' * 64 if changed == 'host' else 'a' * 64
    if changed == 'missing-fingerprint':
        fingerprint = None
    reconnect(owner, pair, fingerprint)
    if changed == 'root':
        owner.watch = tmp_path / 'other-root'
        owner.watch.mkdir()
        (owner.watch / 'pending.bin').write_bytes(b'new root existing file')
        owner._sync_dir_edit.text = lambda: str(owner.watch)
    if changed == 'user':
        context = AuthorizationContext('second', Role.OPERATOR)
    if changed == 'trusted-role':
        context = AuthorizationContext('first', Role.ADMIN)
    if changed == 'store':
        other = UserStore(tmp_path / 'other-users.json')
        other.add_user(user_id='first', display_name='First', role=Role.OPERATOR)
        context = AuthorizationContext('first', Role.OPERATOR, store_path=str(other.path))
    with authorization_scope(context):
        engine = toggle(owner)
    loop(engine, lambda: (owner.watch / 'fresh.bin').write_bytes(b'newly authorised change'))
    assert not (pair.receiver / 'pending.bin').exists(), 'another owner adopted previously queued data'
    assert (pair.receiver / 'fresh.bin').read_bytes() == b'newly authorised change'


@pytest.mark.parametrize('changed', ['role', 'deleted'])
def test_resume_refreshes_the_original_user_and_preserves_pending_data_after_a_refused_start(
        folder_panel, tmp_path, monkeypatch, changed):
    owner, pair = folder_panel
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    with authorization_scope(context):
        loop(toggle(owner))
    disconnect(owner)
    (owner.watch / 'pending.bin').write_bytes(b'retained across refusal')
    reconnect(owner, pair)
    if changed == 'role':
        store.set_role('owner', Role.VIEWER)
    else:
        store.remove_user('owner')
    with monkeypatch.context() as guard:
        guard.setattr(FolderSyncEngine, '_scan', lambda *_args: pytest.fail('revoked resume scanned the watch'))
        with authorization_scope(context):
            assert toggle(owner) is None
    assert len(owner.warnings) == 1 and not (pair.receiver / 'pending.bin').exists()
    if changed == 'role':
        store.set_role('owner', Role.OPERATOR)
    else:
        store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    with authorization_scope(context):
        engine = toggle(owner)
    loop(engine)
    assert (pair.receiver / 'pending.bin').read_bytes() == b'retained across refusal'


def test_explicitly_disabling_sync_resets_the_baseline(folder_panel):
    owner, pair = folder_panel
    loop(toggle(owner))
    toggle(owner, False)
    (owner.watch / 'pending.bin').write_bytes(b'ignored while explicitly disabled')
    engine = toggle(owner)
    loop(engine, lambda: (owner.watch / 'fresh.bin').write_bytes(b'after enabling'))
    assert not (pair.receiver / 'pending.bin').exists()
    assert (pair.receiver / 'fresh.bin').read_bytes() == b'after enabling'


def test_failed_worker_start_does_not_consume_the_retained_baseline(folder_panel, monkeypatch):
    owner, pair = folder_panel
    loop(toggle(owner))
    disconnect(owner)
    (owner.watch / 'pending.bin').write_bytes(b'not lost after start failure')
    reconnect(owner, pair)

    def failed_start(_engine):
        raise OSError('watch temporarily unavailable')

    with monkeypatch.context() as guard:
        guard.setattr(FolderSyncEngine, 'start', failed_start)
        assert toggle(owner) is None
    assert owner.warnings == ['watch temporarily unavailable']
    engine = toggle(owner)
    loop(engine)
    assert (pair.receiver / 'pending.bin').read_bytes() == b'not lost after start failure'


def test_handoff_waits_for_a_blocked_old_sender_and_late_old_work_cannot_adopt_the_new_viewer(
        folder_panel, monkeypatch):
    owner, pair = folder_panel
    monkeypatch.setattr(FolderSyncEngine, 'start', _REAL_START)
    entered, release, delivered = Event(), Event(), Event()
    original = pair.viewer.send_file

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    pair.viewer.send_file = blocked
    engine = toggle(owner)
    assert engine.wait_until_ready()
    (owner.watch / 'pending.bin').write_bytes(b'pending during reconnect')
    assert entered.wait(5)
    worker = engine._thread
    try:
        disconnect(owner)
        assert engine.is_running() and engine.stop_requested
        reconnect(owner, pair)
        with monkeypatch.context() as guard:
            guard.setattr(webrtc_panel, 'make_folder_engine',
                          lambda *_args: pytest.fail('replacement began before the old sender exited'))
            assert toggle(owner) is None
        assert len(owner.warnings) == 1 and 'retired' in owner.warnings[0]
        assert pair.outgoing.sent == []
    finally:
        release.set()
        engine.stop()
    assert worker is not None and not worker.is_alive()
    assert 'pending.bin' not in engine._content.snapshot
    assert pair.outgoing.sent == []
    pair.host.set_file_receipt_callback(lambda _receipt: delivered.set())
    replacement = toggle(owner)
    try:
        assert delivered.wait(5)
        assert (pair.receiver / 'pending.bin').read_bytes() == b'pending during reconnect'
        assert replacement is not engine
    finally:
        replacement.stop()


def test_reconnect_keeps_frozen_receipts_but_rejects_late_callbacks_from_the_old_viewer(folder_panel, monkeypatch):
    from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt

    owner, pair = folder_panel
    old_viewer = owner._viewer
    engine = toggle(owner)
    loop(engine)
    target = owner.watch / 'received.bin'
    target.write_bytes(b'received content')
    received = FileReceiveReceipt(target, sha256(b'received content').hexdigest(), 16)
    callback = old_viewer._file_callbacks.on_receipt
    callback(received)
    disconnect(owner)
    target.write_bytes(b'offline local edit')
    reconnect(owner, pair)
    replacement = toggle(owner)
    with monkeypatch.context() as guard:
        guard.setattr(engine, '_receipt_target', lambda *_args: pytest.fail('old callback accessed the watch'))
        guard.setattr(replacement, '_receipt_target', lambda *_args: pytest.fail('old callback adopted a new engine'))
        callback(received)
    assert replacement._content.snapshot['received.bin'] == sha256(b'received content').hexdigest()
    loop(replacement)
    assert (pair.receiver / 'received.bin').read_bytes() == b'offline local edit'
    assert not (pair.receiver / 'existing.bin').exists(), 'the initial ignored file was sent after reconnect'
