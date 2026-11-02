"""Publication receipts bind original received bytes rather than a later edit to the target path."""
import hashlib
import json
import asyncio
from concurrent.futures import CancelledError
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from headless.test_folder_sync_content import loop
from headless._webrtc_doubles import Channel
from je_auto_control.utils.exception.control_signals import OperationCancelledError
from je_auto_control.utils.remote_desktop import webrtc_files
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.remote_desktop.webrtc_files import FileTransferReceiver


def receive(receiver, content, receipts, *, done=None):
    for message in [json.dumps({'type': 'file_begin', 'name': 'shared.bin', 'size': len(content)}), content,
                    json.dumps({'type': 'file_end'})]:
        receiver.handle_message(message, on_receipt=receipts.append, on_done=done)


@pytest.mark.parametrize('content', [b'', b'one chunk', b'x' * 1024 * 1024], ids=['empty', 'small', 'one_mib'])
def test_receipt_is_frozen_and_describes_received_content_after_atomic_publication(tmp_path, content):
    receipts, done = [], []
    receiver = FileTransferReceiver(tmp_path)
    receive(receiver, content, receipts, done=lambda path: done.append(path.read_bytes()))
    receipt, = receipts
    assert receipt.path == tmp_path / 'shared.bin'
    assert receipt.sha256 == hashlib.sha256(content).hexdigest() and receipt.size == len(content)
    assert done == [content] and receipt.path.read_bytes() == content
    with pytest.raises(FrozenInstanceError):
        receipt.sha256 = '0' * 64


def test_delayed_receipt_does_not_consume_a_local_edit_or_rehash_current_bytes(tmp_path, monkeypatch):
    target = tmp_path / 'shared.bin'
    receiver = FileTransferReceiver(tmp_path)
    receipts, sent = [], []
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, _name: sent.append(Path(path).read_bytes()))

    def received_then_edited():
        receive(receiver, b'received', receipts)
        target.write_bytes(b'newer local edit')
        with monkeypatch.context() as controlled:
            controlled.setattr(engine, '_digest', lambda *_args: pytest.fail('receipt rehashed later file content'))
            assert engine.record_receipt(receipts[0])

    loop(engine, received_then_edited, lambda: None)
    assert sent == [b'newer local edit']


def test_a_receipt_before_first_scan_preserves_a_later_local_edit(tmp_path):
    receipts, sent = [], []
    receiver = FileTransferReceiver(tmp_path)
    receive(receiver, b'received', receipts)
    (tmp_path / 'shared.bin').write_bytes(b'local before baseline')
    engine = FolderSyncEngine(watch_dir=tmp_path, sender=lambda path, _name: sent.append(Path(path).read_bytes()))
    assert engine.record_receipt(receipts[0])
    loop(engine, lambda: None)
    assert sent == [b'local before baseline']


@pytest.mark.parametrize('boundary', ['abort', 'truncated', 'replace_failure', 'short_write'])
def test_failed_receive_has_no_publication_receipt_and_preserves_the_previous_target(tmp_path, monkeypatch, boundary):
    receipts, errors = [], []
    target = tmp_path / 'shared.bin'
    target.write_bytes(b'previous')
    receiver = FileTransferReceiver(tmp_path)
    receiver.handle_message(json.dumps({'type': 'file_begin', 'name': target.name, 'size': 4}))
    if boundary == 'short_write':
        stream = receiver._current['fh']

        class ShortStream:
            def write(self, chunk):
                return stream.write(chunk[:1])

            def close(self):
                stream.close()

        receiver._current['fh'] = ShortStream()
    if boundary == 'replace_failure':
        def failed(*_args):
            raise OSError('controlled publication failure')
        monkeypatch.setattr(webrtc_files.os, 'replace', failed)
    receiver.handle_message(b'part' if boundary != 'truncated' else b'x', on_error=errors.append)
    kind = 'file_abort' if boundary == 'abort' else 'file_end'
    receiver.handle_message(json.dumps({'type': kind}), on_receipt=receipts.append, on_error=errors.append)
    assert errors and receipts == [] and target.read_bytes() == b'previous'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['shared.bin']


@pytest.mark.parametrize('placement', ['outside', 'excluded_subdirectory', 'missing', 'directory'])
def test_receipt_cannot_register_an_unselected_or_missing_path(tmp_path, placement):
    from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt

    watch = tmp_path / 'watch'
    watch.mkdir()
    target = watch / 'shared.bin'
    if placement == 'outside':
        target = tmp_path / 'outside.bin'
    elif placement == 'excluded_subdirectory':
        target = watch / 'subdir' / 'shared.bin'
        target.parent.mkdir()
    if placement == 'directory':
        target.mkdir()
    elif placement != 'missing':
        target.write_bytes(b'received')
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda *_args: None)
    receipt = FileReceiveReceipt(target, hashlib.sha256(b'received').hexdigest(), 8)
    assert not engine.record_receipt(receipt) and engine._content.snapshot == {}


@pytest.mark.parametrize('digest,size', [('bad', 1), ('G' * 64, 1), ('0' * 64, -1), ('0' * 64, True),
                                        ('0' * 64, 1.5)])
def test_malformed_publication_metadata_uses_the_flat_framework_error_family(tmp_path, digest, size):
    from je_auto_control.utils.exception.exceptions import AutoControlException
    from je_auto_control.utils.remote_desktop.file_receipts import FileReceiptError, FileReceiveReceipt

    with pytest.raises(FileReceiptError) as caught:
        FileReceiveReceipt(tmp_path / 'shared.bin', digest, size)
    assert isinstance(caught.value, AutoControlException)


def test_receipt_hashes_streamed_chunks_without_rereading_the_published_path(tmp_path, monkeypatch):
    original_open = Path.open
    receipts = []
    receiver = FileTransferReceiver(tmp_path)

    def no_read(path, mode='r', *args, **kwargs):
        assert 'r' not in mode, 'receiver rehashed the published file on the bridge thread'
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as controlled:
        controlled.setattr(Path, 'open', no_read)
        receive(receiver, b'streamed content', receipts)
    assert receipts[0].sha256 == hashlib.sha256(b'streamed content').hexdigest()


def test_relative_inbox_remains_bound_when_another_operation_changes_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    receiver = FileTransferReceiver(Path('inbox'))
    receiver.handle_message(json.dumps({'type': 'file_begin', 'name': 'shared.bin', 'size': 4}))
    changed = tmp_path / 'other-cwd'
    changed.mkdir()
    monkeypatch.chdir(changed)
    receipts = []
    receiver.handle_message(b'data')
    receiver.handle_message(json.dumps({'type': 'file_end'}), on_receipt=receipts.append)
    assert len(receipts) == 1 and receipts[0].path == tmp_path / 'inbox' / 'shared.bin'
    assert receipts[0].path.read_bytes() == b'data' and list(changed.iterdir()) == []


def test_relative_watch_keeps_its_original_selected_root_when_cwd_changes(tmp_path, monkeypatch):
    original = tmp_path / 'original'
    original.mkdir()
    monkeypatch.chdir(original)
    watch = original / 'watch'
    watch.mkdir()
    receipts, sent = [], []
    engine = FolderSyncEngine(watch_dir=Path('watch'), sender=lambda path, _name: sent.append(Path(path).read_bytes()))
    receive(FileTransferReceiver(Path('watch')), b'received', receipts)
    changed = tmp_path / 'other-cwd'
    (changed / 'watch').mkdir(parents=True)
    sentinel = changed / 'watch' / 'shared.bin'
    sentinel.write_bytes(b'unselected content')
    monkeypatch.chdir(changed)
    assert engine.record_receipt(receipts[0])
    (watch / 'shared.bin').write_bytes(b'original watch edit')
    loop(engine, lambda: None)
    assert sent == [b'original watch edit'] and sentinel.read_bytes() == b'unselected content'


@pytest.fixture(params=['host', 'viewer'])
def native_receiver(request, tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop import webrtc_host, webrtc_viewer

    monkeypatch.setattr(webrtc_files, 'default_inbox_dir', lambda: tmp_path)
    monkeypatch.setattr(webrtc_host, 'default_audit_log', lambda: SimpleNamespace(log=lambda *_args, **_kwargs: None))
    if request.param == 'host':
        owner = webrtc_host.WebRTCDesktopHost(token='controlled', inbox_dir=tmp_path)
    else:
        owner = webrtc_viewer.WebRTCDesktopViewer(token='controlled')
    owner._pc, owner._authenticated = object(), True
    channel = Channel('files', ready_state='open')
    owner._wire_files_channel(channel)
    yield owner, channel, tmp_path
    owner._files_receiver.close()


def native_deliver(channel, content=b'bytes'):
    for message in [json.dumps({'type': 'file_begin', 'name': 'shared.bin', 'size': len(content)}), content,
                    json.dumps({'type': 'file_end'})]:
        channel.fire('message', message)


def test_native_receipt_listener_can_be_replaced_and_cleared_without_changing_path_notifications(native_receiver):
    owner, channel, inbox = native_receiver
    first, second, paths = [], [], []
    owner.set_file_received_callback(paths.append)
    owner.set_file_receipt_callback(first.append)
    native_deliver(channel, b'first')
    owner.set_file_receipt_callback(second.append)
    native_deliver(channel, b'second')
    owner.set_file_receipt_callback(None)
    native_deliver(channel, b'third')
    assert len(first) == len(second) == 1 and len(paths) == 3
    assert first[0].sha256 == hashlib.sha256(b'first').hexdigest()
    assert second[0].sha256 == hashlib.sha256(b'second').hexdigest()
    assert (inbox / 'shared.bin').read_bytes() == b'third'


def test_native_ordinary_receipt_callback_failure_still_delivers_the_path_notice(native_receiver):
    owner, channel, inbox = native_receiver
    paths = []

    def failed(_receipt):
        raise RuntimeError('controlled receipt listener failure')

    owner.set_file_receipt_callback(failed)
    owner.set_file_received_callback(paths.append)
    native_deliver(channel)
    assert paths == [inbox / 'shared.bin'] and paths[0].read_bytes() == b'bytes'


@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, asyncio.CancelledError,
                                  CancelledError, OperationCancelledError])
def test_native_receipt_callback_preserves_wrapped_controls_after_publication(native_receiver, signal):
    owner, channel, inbox = native_receiver
    original = signal('controlled')

    def failed(_receipt):
        raise RuntimeError('wrapped receipt callback') from original

    owner.set_file_receipt_callback(failed)
    with pytest.raises(signal) as caught:
        native_deliver(channel)
    assert caught.value is original and (inbox / 'shared.bin').read_bytes() == b'bytes'
    assert list(inbox.glob('*.part')) == []
