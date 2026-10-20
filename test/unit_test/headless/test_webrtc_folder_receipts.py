"""Actual native viewer/GUI receipt wiring suppresses received bytes while preserving later local edits."""
import json
from types import SimpleNamespace

import pytest

pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from headless._webrtc_doubles import Bridge, Channel, FakePeerConnection
from headless.test_folder_sync_content import loop
from je_auto_control.gui.remote_desktop import webrtc_panel
from je_auto_control.gui.remote_desktop.folder_sync_io import make_folder_engine
from je_auto_control.utils.rbac import AuthorizationContext, Role, UserStore, authorization_scope
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.remote_desktop import webrtc_files
from je_auto_control.utils.remote_desktop.webrtc_transport import WebRTCConfig


@pytest.fixture
def native_folder(tmp_path, monkeypatch):
    watch = tmp_path / 'watch'
    watch.mkdir()
    store = UserStore(tmp_path / 'users.json')
    store.add_user(user_id='owner', display_name='Owner', role=Role.OPERATOR)
    monkeypatch.setattr(webrtc_files, 'get_bridge', Bridge)
    monkeypatch.setattr(webrtc_files, 'default_inbox_dir', lambda: watch)
    monkeypatch.setattr(webrtc_panel, '_read_webrtc_config', lambda _owner: WebRTCConfig())
    notices = []
    signals = SimpleNamespace(**{name: SimpleNamespace(emit=lambda *_args: None)
                                 for name in ['state', 'auth', 'inbox_listing', 'inbox_op']})
    owner = SimpleNamespace(_viewer_id='controlled', _on_av_frame=lambda _frame: None, _signals=signals,
                            _on_received_file=notices.append, _viewer=None, _sync_engine=None,
                            watch=watch, store=store, _sync_dir_edit=SimpleNamespace(text=lambda: str(watch)),
                            _sync_btn=SimpleNamespace(setText=lambda _text: None, setChecked=lambda _value: None))
    viewer = webrtc_panel._WebRTCViewerPanel._build_viewer(owner, 'controlled')
    owner._viewer = viewer
    viewer._pc = FakePeerConnection()
    viewer._authenticated = True
    channel = Channel('files', ready_state='open')
    viewer._wire_files_channel(channel)
    owner._require_viewer = lambda: viewer
    context = AuthorizationContext('owner', Role.OPERATOR, store_path=str(store.path))
    monkeypatch.setattr(FolderSyncEngine, 'start', lambda _engine: None)
    with authorization_scope(context):
        webrtc_panel._WebRTCViewerPanel._on_toggle_sync(owner, True)
    engine = owner._sync_engine
    yield owner, viewer, engine, channel, notices
    engine.stop()
    viewer._files_receiver.close()


def deliver(channel, content=b'remote bytes'):
    channel.fire('message', json.dumps({'type': 'file_begin', 'name': 'shared.bin', 'size': len(content)}))
    channel.fire('message', content)
    channel.fire('message', json.dumps({'type': 'file_end'}))


def test_native_gui_receipt_does_not_echo_and_later_local_bytes_still_send(native_folder):
    owner, _viewer, engine, channel, notices = native_folder
    target = owner.watch / 'shared.bin'
    loop(engine, lambda: deliver(channel), lambda: target.write_bytes(b'local edit'), lambda: None)
    sent = [message for message in channel.sent if isinstance(message, bytes)]
    assert sent == [b'local edit'], 'the GUI folder mirror echoed received bytes or consumed a local edit'
    assert notices == [target]


@pytest.mark.parametrize('invalidated', ['viewer', 'engine', 'role', 'authentication', 'connection', 'stop'])
def test_delayed_native_receipt_does_not_read_or_adopt_a_detached_owner(native_folder, monkeypatch, invalidated):
    from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt
    import hashlib

    owner, viewer, engine, _channel, _notices = native_folder
    target = owner.watch / 'shared.bin'
    target.write_bytes(b'received')
    callback = viewer._file_callbacks.on_receipt
    if invalidated == 'viewer':
        owner._viewer = None
    elif invalidated == 'engine':
        owner._sync_engine = make_folder_engine(viewer, str(owner.watch), lambda: owner._viewer,
                                               lambda: owner._sync_engine)
    elif invalidated == 'role':
        owner.store.set_role('owner', Role.VIEWER)
    elif invalidated == 'authentication':
        viewer._authenticated = False
    elif invalidated == 'connection':
        viewer._pc = FakePeerConnection()
    else:
        engine.request_stop()
    monkeypatch.setattr(engine, '_receipt_target', lambda _path: pytest.fail('detached receipt read the watch'))
    callback(FileReceiveReceipt(target, hashlib.sha256(b'received').hexdigest(), 8))
    assert engine._content.snapshot == {}
    if owner._sync_engine is not engine and owner._sync_engine is not None:
        assert owner._sync_engine._content.snapshot == {}


@pytest.mark.parametrize('reply_during_send', [False, True])
def test_native_two_way_folder_receipts_converge_without_echo_or_lost_reply(
        native_folder, tmp_path, monkeypatch, reply_during_send):
    from je_auto_control.utils.remote_desktop import webrtc_host

    owner, _viewer, engine_a, channel_a, notices = native_folder
    watch_b = tmp_path / 'peer-b'
    watch_b.mkdir()
    monkeypatch.setattr(webrtc_host, 'default_audit_log', lambda: SimpleNamespace(log=lambda *_args, **_kwargs: None))
    host = webrtc_host.WebRTCDesktopHost(token='controlled', inbox_dir=watch_b)
    host._pc, host._authenticated = object(), True
    channel_b = Channel('files', ready_state='open')
    host._wire_files_channel(channel_b)
    engine_b = FolderSyncEngine(watch_dir=watch_b, sender=lambda path, name: host.push_file(path, remote_name=name))
    edited = False

    def received_b(receipt):
        nonlocal edited
        assert engine_b.record_receipt(receipt)
        if reply_during_send and not edited:
            edited = True
            (watch_b / 'shared.bin').write_bytes(b'local B')
            loop(engine_b, lambda: None)

    def send_a(message):
        channel_a.sent.append(message)
        channel_b.fire('message', message)

    def send_b(message):
        channel_b.sent.append(message)
        channel_a.fire('message', message)

    host.set_file_receipt_callback(received_b)
    channel_a.send, channel_b.send = send_a, send_b

    def edit_b():
        def edited_b():
            (watch_b / 'shared.bin').write_bytes(b'local B')
        loop(engine_b, edited_b, lambda: None)

    try:
        transition = (lambda: None) if reply_during_send else edit_b
        loop(engine_a, lambda: (owner.watch / 'shared.bin').write_bytes(b'local A'), transition, lambda: None)
        assert (owner.watch / 'shared.bin').read_bytes() == (watch_b / 'shared.bin').read_bytes() == b'local B'
        assert [message for message in channel_a.sent if isinstance(message, bytes)] == [b'local A']
        assert [message for message in channel_b.sent if isinstance(message, bytes)] == [b'local B']
        assert notices == [owner.watch / 'shared.bin']
    finally:
        engine_b.stop()
        host._files_receiver.close()
