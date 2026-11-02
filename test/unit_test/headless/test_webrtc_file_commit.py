"""Native folder delivery requires a publication receipt, not merely acceptance into the channel queue."""
import asyncio
from concurrent.futures import CancelledError
import hashlib
import json
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from headless._webrtc_doubles import Channel, FakePeerConnection
from headless.test_folder_sync_content import loop
from headless.test_webrtc_file_delivery import bridge as bridge
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.remote_desktop import webrtc_files, webrtc_host, webrtc_viewer
from je_auto_control.utils.remote_desktop import webrtc_file_commit
from je_auto_control.utils.exception.control_signals import OperationCancelledError


@pytest.fixture(autouse=True)
def bounded_waits(monkeypatch):
    monkeypatch.setattr(webrtc_file_commit, '_PROBE_TIMEOUT_S', .5)
    monkeypatch.setattr(webrtc_file_commit, '_COMMIT_TIMEOUT_S', .5)


@pytest.fixture
def native_pair(bridge, tmp_path, monkeypatch):
    active, failures = bridge
    monkeypatch.setattr(webrtc_host, 'get_bridge', lambda: active)
    monkeypatch.setattr(webrtc_viewer, 'get_bridge', lambda: active)
    monkeypatch.setattr(webrtc_files, 'default_inbox_dir', lambda: tmp_path / 'local-inbox')
    monkeypatch.setattr(webrtc_host, 'default_audit_log', lambda: SimpleNamespace(log=lambda *_args, **_kwargs: None))
    state = SimpleNamespace(drop_data=False, drop_end=False, drop_ack=False, corrupt_data=False, tamper_ack=None,
                            after_ack=None, tamper_support=None, sent=[], held=[], held_acks=[],
                            end_held=Event(), ack_held=Event(),
                            receiver=tmp_path / 'remote-inbox', bridge=active)

    class Link(Channel):
        def send(self, message):
            self.sent.append(message)
            state.sent.append((self.label, message))
            envelope = json.loads(message) if isinstance(message, str) else {}
            if self.label == 'inbound' and envelope.get('type') == 'file_support' and state.tamper_support is not None:
                message = json.dumps(state.tamper_support(envelope))
            if self.label == 'outbound' and isinstance(message, bytes) and state.drop_data:
                return
            if self.label == 'outbound' and envelope.get('type') == 'file_end' and state.drop_end:
                state.held.append(message)
                state.end_held.set()
                return
            if self.label == 'outbound' and isinstance(message, bytes) and state.corrupt_data:
                message = b'X' + message[1:]
            if self.label == 'inbound' and envelope.get('type') == 'file_commit':
                if state.tamper_ack is not None:
                    message = json.dumps(state.tamper_ack(envelope))
                if state.drop_ack:
                    state.held_acks.append(message)
                    state.ack_held.set()
                    return
            asyncio.get_running_loop().call_soon(self.peer.fire, 'message', message)
            if self.label == 'inbound' and envelope.get('type') == 'file_commit' and state.after_ack is not None:
                asyncio.get_running_loop().call_soon(state.after_ack)

    async def setup():
        viewer = webrtc_viewer.WebRTCDesktopViewer(token='controlled')
        host = webrtc_host.WebRTCDesktopHost(token='controlled', inbox_dir=state.receiver)
        viewer._pc, host._pc = FakePeerConnection(), FakePeerConnection()
        viewer._authenticated = host._authenticated = True
        outgoing, incoming = Link('outbound', 'open'), Link('inbound', 'open')
        outgoing.peer, incoming.peer = incoming, outgoing
        viewer._wire_files_channel(outgoing)
        host._wire_files_channel(incoming)
        return viewer, host, outgoing, incoming

    viewer, host, outgoing, incoming = active.submit(setup()).result(5)
    state.viewer, state.host, state.outgoing, state.incoming = viewer, host, outgoing, incoming
    yield state
    active.submit(viewer._async_stop()).result(5)
    active.submit(host._async_stop()).result(5)
    assert failures == []


def test_accepted_but_dropped_bytes_do_not_advance_folder_delivery_state(native_pair, tmp_path):
    watch = tmp_path / 'source'
    watch.mkdir()
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda path, name: native_pair.viewer.send_file(
        path, remote_name=name, require_commit=True))
    native_pair.drop_data = True
    target = watch / 'payload.bin'
    loop(engine, lambda: target.write_bytes(b'must reach the remote target'), lambda: None)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    assert engine._content.snapshot.get(target.name) != digest, 'queued bytes were falsely marked remotely published'
    assert list(native_pair.receiver.iterdir()) == []


def sending(pair, source, **options):
    result = SimpleNamespace(done=Event(), errors=[])

    def send():
        try:
            pair.viewer.send_file(source, require_commit=True, **options)
        except BaseException as error:
            result.errors.append(error)
        finally:
            result.done.set()

    result.worker = Thread(target=send)
    result.worker.start()
    return result


def finished(result):
    assert result.done.wait(5)
    result.worker.join(5)
    assert not result.worker.is_alive()


def flush(pair):
    pair.bridge.submit(asyncio.sleep(0)).result(5)


def test_confirmation_waits_for_remote_end_and_atomic_publication(native_pair, tmp_path):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'confirmed bytes')
    native_pair.drop_end = True
    result = sending(native_pair, source)
    try:
        assert native_pair.end_held.wait(5)
        assert not result.done.wait(.05) and not (native_pair.receiver / source.name).exists()
        native_pair.bridge.call_soon(native_pair.incoming.fire, 'message', native_pair.held.pop())
        finished(result)
        assert result.errors == [] and (native_pair.receiver / source.name).read_bytes() == source.read_bytes()
    finally:
        finished(result)


def test_a_failed_confirmed_folder_send_retries_and_advances_only_after_publication(native_pair, tmp_path):
    watch = tmp_path / 'source'
    watch.mkdir()
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda path, name: native_pair.viewer.send_file(
        path, remote_name=name, require_commit=True))
    native_pair.drop_data = True

    def reconnect():
        assert 'payload.bin' not in engine._content.snapshot
        native_pair.drop_data = False

    loop(engine, lambda: (watch / 'payload.bin').write_bytes(b'retried bytes'), reconnect, lambda: None)
    assert engine._content.snapshot['payload.bin'] == hashlib.sha256(b'retried bytes').hexdigest()
    assert (native_pair.receiver / 'payload.bin').read_bytes() == b'retried bytes'


def test_an_unsupported_peer_is_refused_before_source_metadata_and_manual_send_still_works(
        native_pair, tmp_path, monkeypatch):
    legacy = webrtc_files.FileTransferReceiver(native_pair.receiver)
    native_pair.incoming.handlers['message'] = legacy.handle_message
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'legacy bytes')
    original_is_file = Path.is_file
    reads = []

    def metadata(path):
        if path == source:
            reads.append(True)
        return original_is_file(path)

    monkeypatch.setattr(Path, 'is_file', metadata)
    with pytest.raises(webrtc_files.FileTransferError):
        native_pair.viewer.send_file(source, require_commit=True)
    assert reads == [] and list(native_pair.receiver.iterdir()) == []
    native_pair.viewer.send_file(source)
    flush(native_pair)
    assert (native_pair.receiver / source.name).read_bytes() == b'legacy bytes'
    begins = [json.loads(message) for label, message in native_pair.sent
              if label == 'outbound' and isinstance(message, str) and json.loads(message).get('type') == 'file_begin']
    assert len(begins) == 1 and 'commit' not in begins[0]


@pytest.mark.parametrize('field,value', [('sha256', '0' * 64), ('size', 0), ('size', True)])
def test_a_mismatched_publication_receipt_never_confirms_sent_bytes(native_pair, tmp_path, field, value):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'published but not correctly acknowledged')
    native_pair.tamper_ack = lambda envelope: {**envelope, field: value}
    with pytest.raises(webrtc_files.FileTransferError):
        native_pair.viewer.send_file(source, require_commit=True)
    assert (native_pair.receiver / source.name).read_bytes() == source.read_bytes()


def test_corrupted_chunks_fail_checksum_before_replacing_an_existing_target(native_pair, tmp_path):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'original bytes')
    target = native_pair.receiver / source.name
    target.write_bytes(b'previous target')
    native_pair.corrupt_data = True
    receipts = []
    native_pair.host.set_file_receipt_callback(receipts.append)
    with pytest.raises(webrtc_files.FileTransferError):
        native_pair.viewer.send_file(source, require_commit=True)
    flush(native_pair)
    assert target.read_bytes() == b'previous target' and receipts == []
    assert sorted(path.name for path in native_pair.receiver.iterdir()) == [source.name]


@pytest.mark.parametrize('boundary', ['files_close', 'control_close', 'stop', 'permission_revoke_regrant'])
def test_pending_confirmation_fails_when_its_owner_ends_and_partial_target_is_preserved(
        native_pair, tmp_path, boundary):
    from je_auto_control.utils.remote_desktop.permissions import SessionPermissions

    source = tmp_path / 'payload.bin'
    source.write_bytes(b'partial bytes')
    target = native_pair.receiver / source.name
    target.write_bytes(b'previous target')
    native_pair.drop_end = True
    result = sending(native_pair, source)
    assert native_pair.end_held.wait(5)

    async def ended():
        if boundary == 'files_close':
            for channel in (native_pair.outgoing, native_pair.incoming):
                channel.readyState = 'closed'
                channel.fire('close')
        elif boundary == 'control_close':
            control = Channel('ctrl')
            native_pair.viewer._control_channel = control
            native_pair.viewer._wire_control_channel(control)
            control.fire('close')
        elif boundary == 'stop':
            await native_pair.viewer._async_stop()
        else:
            native_pair.host.set_permissions(SessionPermissions.none())
            native_pair.host.set_permissions(SessionPermissions.full_control())
            native_pair.incoming.fire('message', native_pair.held.pop())

    native_pair.bridge.submit(ended()).result(5)
    finished(result)
    flush(native_pair)
    assert len(result.errors) == 1 and isinstance(result.errors[0], webrtc_files.FileTransferError)
    assert target.read_bytes() == b'previous target'
    assert sorted(path.name for path in native_pair.receiver.iterdir()) == [source.name]


def test_old_acknowledgement_cannot_confirm_a_reused_transfer_id(native_pair, tmp_path, monkeypatch):
    original_token = webrtc_files.secrets.token_hex
    monkeypatch.setattr(webrtc_files.secrets, 'token_hex', lambda size: 'a' * 16 if size == 8 else original_token(size))
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'identical bytes')
    native_pair.drop_ack = True
    first = sending(native_pair, source)
    finished(first)
    assert len(first.errors) == 1
    old_ack, = native_pair.held_acks
    native_pair.held_acks.clear()
    native_pair.ack_held.clear()
    native_pair.drop_ack = False
    native_pair.drop_data = native_pair.drop_end = True
    native_pair.end_held.clear()
    second = sending(native_pair, source, remote_name='second.bin')
    try:
        assert native_pair.end_held.wait(5)
        native_pair.bridge.call_soon(native_pair.outgoing.fire, 'message', old_ack)
        assert not second.done.wait(.05), 'an old transfer receipt confirmed a replacement request'
        native_pair.bridge.call_soon(native_pair.incoming.fire, 'message', native_pair.held.pop())
        finished(second)
        assert len(second.errors) == 1 and isinstance(second.errors[0], webrtc_files.FileTransferError)
        assert not (native_pair.receiver / 'second.bin').exists()
    finally:
        finished(second)
    native_pair.drop_data = native_pair.drop_end = False
    native_pair.viewer.send_file(source, remote_name='second.bin', require_commit=True)
    assert (native_pair.receiver / 'second.bin').read_bytes() == source.read_bytes()


def test_completed_publication_receipt_wins_over_late_cancellation(native_pair, tmp_path):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'committed')
    cancelled = Event()
    native_pair.after_ack = cancelled.set
    native_pair.viewer.send_file(source, require_commit=True, cancelled=cancelled.is_set)
    assert cancelled.is_set() and (native_pair.receiver / source.name).read_bytes() == b'committed'


@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, asyncio.CancelledError,
                                  CancelledError, OperationCancelledError])
def test_original_wrapped_cancellation_while_awaiting_commit_is_preserved(native_pair, tmp_path, signal):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'pending publication')
    target = native_pair.receiver / source.name
    target.write_bytes(b'previous target')
    native_pair.drop_end = True
    original = signal('controlled')

    def cancelled():
        if native_pair.end_held.is_set():
            raise RuntimeError('wrapped confirmation cancellation') from original
        return False

    result = sending(native_pair, source, cancelled=cancelled)
    finished(result)
    flush(native_pair)
    assert len(result.errors) == 1 and result.errors[0] is original
    assert target.read_bytes() == b'previous target'
    assert sorted(path.name for path in native_pair.receiver.iterdir()) == [source.name]


def test_pending_commit_still_owns_the_channel_and_refuses_a_second_producer(native_pair, tmp_path):
    one, two = tmp_path / 'one.bin', tmp_path / 'two.bin'
    one.write_bytes(b'first')
    two.write_bytes(b'second')
    native_pair.drop_ack = True
    result = sending(native_pair, one)
    try:
        assert native_pair.ack_held.wait(5)
        count = len(native_pair.sent)
        with pytest.raises(webrtc_files.FileTransferError):
            native_pair.viewer.send_file(two, require_commit=True)
        assert len(native_pair.sent) == count and not result.done.is_set()
        native_pair.bridge.call_soon(native_pair.outgoing.fire, 'message', native_pair.held_acks.pop())
        finished(result)
        assert result.errors == [] and not (native_pair.receiver / two.name).exists()
    finally:
        finished(result)


def test_confirmed_send_on_the_bridge_thread_refuses_before_source_metadata(native_pair, tmp_path, monkeypatch):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'no event-loop deadlock')
    original = Path.is_file

    def forbidden(path):
        assert path != source, 'a rejected loop-thread send read source metadata'
        return original(path)

    monkeypatch.setattr(Path, 'is_file', forbidden)

    async def call():
        with pytest.raises(webrtc_files.FileTransferError):
            native_pair.viewer.send_file(source, require_commit=True)

    native_pair.bridge.submit(call()).result(5)
    assert native_pair.sent == []


def test_replaced_bridge_epoch_cannot_probe_or_read_through_an_old_native_channel(native_pair, tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop.webrtc_transport import _AsyncioBridge

    source = tmp_path / 'payload.bin'
    source.write_bytes(b'old epoch')
    original = Path.is_file
    replacement = _AsyncioBridge()

    def forbidden(path):
        assert path != source, 'a stale native channel read source metadata'
        return original(path)

    monkeypatch.setattr(Path, 'is_file', forbidden)
    with monkeypatch.context() as controlled:
        controlled.setattr(webrtc_files, 'get_bridge', lambda: replacement)
        try:
            with pytest.raises(webrtc_files.FileTransferError):
                native_pair.viewer.send_file(source, require_commit=True)
        finally:
            replacement.stop()
    assert native_pair.sent == []


@pytest.mark.parametrize('message', ['[1,2]', '{"type":[]}', 'x' * 4097,
                                   '{"type":"file_probe","version":true,"nonce":"bad"}'],
                         ids=['array', 'bad_type', 'oversized', 'bad_probe'])
def test_malformed_native_control_frame_cleans_partial_and_does_not_escape_onto_the_loop(native_pair, message):
    target = native_pair.receiver / 'payload.bin'
    target.write_bytes(b'previous')

    async def malformed():
        channel = native_pair.incoming
        channel.fire('message', json.dumps({'type': 'file_begin', 'name': target.name, 'size': 4}))
        channel.fire('message', b'pa')
        channel.fire('message', message)

    native_pair.bridge.submit(malformed()).result(5)
    assert target.read_bytes() == b'previous'
    assert sorted(p.name for p in native_pair.receiver.iterdir()) == [target.name]


def test_global_confirmation_lookup_does_not_keep_unused_channels_or_bindings_alive(tmp_path):
    import gc
    import weakref
    from je_auto_control.utils.remote_desktop.webrtc_file_receive import bind_file_receiver

    channel = Channel('files', 'open')
    receiver = webrtc_files.FileTransferReceiver(tmp_path)
    bind_file_receiver(channel, receiver, lambda: True, lambda _path: None)
    identifier = id(channel)
    reference = weakref.ref(webrtc_file_commit._find_binding(channel))
    del channel, receiver
    gc.collect()
    assert reference() is None and identifier not in webrtc_file_commit._bindings


@pytest.mark.parametrize('content', [b'', b'small file', b'Z' * (2 * 1024 * 1024)], ids=['empty', 'small', 'two_mib'])
def test_confirmed_native_transfer_publishes_exact_empty_small_or_large_content(native_pair, tmp_path, content):
    source = tmp_path / 'payload.bin'
    source.write_bytes(content)
    native_pair.viewer.send_file(source, require_commit=True)
    assert (native_pair.receiver / source.name).read_bytes() == content


@pytest.mark.parametrize('version', [True, 3, '2'])
def test_unconfirmed_capability_version_is_refused_before_source_metadata(native_pair, tmp_path, monkeypatch, version):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'source must remain unread')
    native_pair.tamper_support = lambda envelope: {**envelope, 'version': version}
    original = Path.is_file

    def forbidden(path):
        assert path != source, 'unconfirmed peer read source metadata'
        return original(path)

    monkeypatch.setattr(Path, 'is_file', forbidden)
    with pytest.raises(webrtc_files.FileTransferError):
        native_pair.viewer.send_file(source, require_commit=True)


def test_every_confirmed_file_rechecks_remote_file_permission_before_reading_source(native_pair, tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop.permissions import SessionPermissions

    first, second = tmp_path / 'first.bin', tmp_path / 'second.bin'
    first.write_bytes(b'first')
    second.write_bytes(b'second')
    native_pair.viewer.send_file(first, require_commit=True)

    async def permissions(allowed):
        native_pair.host.set_permissions(SessionPermissions.full_control() if allowed else SessionPermissions.none())

    native_pair.bridge.submit(permissions(False)).result(5)
    original = Path.is_file

    def forbidden(path):
        assert path != second, 'a cached capability bypassed the revoked file permission'
        return original(path)

    with monkeypatch.context() as controlled:
        controlled.setattr(Path, 'is_file', forbidden)
        with pytest.raises(webrtc_files.FileTransferError):
            native_pair.viewer.send_file(second, require_commit=True)
    native_pair.bridge.submit(permissions(True)).result(5)
    native_pair.viewer.send_file(second, require_commit=True)
    assert (native_pair.receiver / second.name).read_bytes() == b'second'


@pytest.mark.parametrize('where,field,value', [
    ('begin', 'commit', True), ('begin', 'commit', 2.0), ('begin', 'commit', 3),
    ('begin', 'size', True), ('begin', 'size', '4'), ('begin', 'transfer_id', 'bad'),
    ('end', 'transfer_id', 'b' * 16), ('end', 'sha256', 'bad'), ('end', 'sha256', '0' * 64),
    ('end', 'commit_nonce', 'bad'),
])
def test_confirmed_receiver_validates_metadata_and_digest_before_publication(tmp_path, where, field, value):
    receiver = webrtc_files.FileTransferReceiver(tmp_path)
    target = tmp_path / 'payload.bin'
    target.write_bytes(b'previous')
    begin = {'type': 'file_begin', 'name': target.name, 'size': 4, 'commit': 2, 'transfer_id': 'a' * 16}
    end = {'type': 'file_end', 'transfer_id': 'a' * 16, 'commit_nonce': 'b' * 32,
           'sha256': hashlib.sha256(b'data').hexdigest()}
    selected = begin if where == 'begin' else end
    selected[field] = value
    receipts, errors = [], []
    for message in (json.dumps(begin), b'data', json.dumps(end)):
        receiver.handle_message(message, on_receipt=receipts.append, on_error=errors.append)
    assert receipts == [] and errors and target.read_bytes() == b'previous'
    assert sorted(path.name for path in tmp_path.iterdir()) == [target.name]


@pytest.mark.parametrize('value', [0, 1, 'yes', None])
def test_confirmation_mode_rejects_nonboolean_values_without_sending_any_frame(native_pair, tmp_path, value):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'no coercion')
    with pytest.raises(webrtc_files.FileTransferError, match='boolean'):
        native_pair.viewer.send_file(source, require_commit=value)
    assert native_pair.sent == []


def test_relative_source_is_bound_before_the_capability_exchange_changes_cwd(native_pair, tmp_path, monkeypatch):
    first, second = tmp_path / 'source-a', tmp_path / 'source-b'
    first.mkdir()
    second.mkdir()
    (first / 'payload.bin').write_bytes(b'from A')
    (second / 'payload.bin').write_bytes(b'from B')
    monkeypatch.chdir(first)

    def changed(envelope):
        monkeypatch.chdir(second)
        return envelope

    native_pair.tamper_support = changed
    native_pair.viewer.send_file('payload.bin', require_commit=True)
    assert (native_pair.receiver / 'payload.bin').read_bytes() == b'from A'
