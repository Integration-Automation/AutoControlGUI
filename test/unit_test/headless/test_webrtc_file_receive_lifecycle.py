"""Partial file ownership ends on close, permission loss and replacement of the originating channel."""
import asyncio
import json
from concurrent.futures import CancelledError
from threading import Event, Thread

import pytest

from headless._webrtc_doubles import Channel, FakePeerConnection
from je_auto_control.utils.remote_desktop import webrtc_files
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
from je_auto_control.utils.remote_desktop.webrtc_files import FileTransferReceiver
from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost
from je_auto_control.utils.remote_desktop.webrtc_viewer import WebRTCDesktopViewer
from je_auto_control.utils.exception.control_signals import OperationCancelledError


def begin(name='payload.bin', size=8):
    return json.dumps({'type': 'file_begin', 'name': name, 'size': size})


def end():
    return json.dumps({'type': 'file_end'})


@pytest.fixture(params=['host', 'viewer'])
def endpoint(request, tmp_path, monkeypatch):
    inbox = tmp_path / 'inbox'
    monkeypatch.setattr(webrtc_files, 'default_inbox_dir', lambda: inbox)
    if request.param == 'host':
        owner = WebRTCDesktopHost(token='controlled', inbox_dir=inbox)
    else:
        owner = WebRTCDesktopViewer(token='controlled')
    owner._pc = FakePeerConnection()
    owner._authenticated = True
    channel = Channel('files', ready_state='open')
    owner._files_channel = channel
    owner._wire_files_channel(channel)
    yield owner, channel, inbox
    asyncio.run(owner._async_stop())


def test_receiver_close_discards_partial_and_refuses_late_frames(tmp_path):
    receiver = FileTransferReceiver(tmp_path)
    target = tmp_path / 'payload.bin'
    target.write_bytes(b'previous')
    receiver.handle_message(begin())
    receiver.handle_message(b'half')
    receiver.close()
    receiver.close()
    for message in (b'late', end(), begin('late.bin', 0), end()):
        receiver.handle_message(message)
    assert target.read_bytes() == b'previous'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['payload.bin']


def test_close_serializes_with_a_chunk_write_instead_of_closing_its_open_file(tmp_path):
    receiver = FileTransferReceiver(tmp_path)
    receiver.handle_message(begin())
    stream = receiver._current['fh']
    writing, release, closed = Event(), Event(), Event()
    errors = []

    class PausedStream:
        def write(self, chunk):
            writing.set()
            assert release.wait(5)
            return stream.write(chunk)

        def close(self):
            stream.close()

    receiver._current['fh'] = PausedStream()

    def write():
        try:
            receiver.handle_message(b'half')
        except Exception as error:
            errors.append(error)

    def close():
        try:
            receiver.close()
        except Exception as error:
            errors.append(error)
        finally:
            closed.set()

    writer, closer = Thread(target=write), Thread(target=close)
    writer.start()
    assert writing.wait(5)
    closer.start()
    try:
        assert not closed.wait(.1), 'close raced an in-flight write'
    finally:
        release.set()
        writer.join(5)
        closer.join(5)
    assert not writer.is_alive() and not closer.is_alive() and errors == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('boundary', ['stop', 'channel_close'])
def test_stopping_the_owner_or_channel_removes_partial_bytes(endpoint, boundary):
    owner, channel, inbox = endpoint
    channel.fire('message', begin())
    channel.fire('message', b'half')
    assert list(inbox.glob('*.part'))
    if boundary == 'stop':
        asyncio.run(owner._async_stop())
    else:
        channel.fire('close')
    assert list(inbox.iterdir()) == []
    channel.fire('message', begin('late.bin', 0))
    channel.fire('message', end())
    assert list(inbox.iterdir()) == []


def test_replaced_files_channel_cannot_finish_or_abort_the_new_transfer(endpoint):
    owner, old, inbox = endpoint
    old.fire('message', begin('old.bin'))
    old.fire('message', b'old')
    current = Channel('files', ready_state='open')
    owner._files_channel = current
    owner._wire_files_channel(current)
    current.fire('message', begin('new.bin', 4))
    current.fire('message', b'new!')
    old.fire('message', end())
    old.fire('message', json.dumps({'type': 'file_abort'}))
    old.fire('close')
    current.fire('message', end())
    assert sorted(p.name for p in inbox.iterdir()) == ['new.bin']
    assert (inbox / 'new.bin').read_bytes() == b'new!'


def test_changed_concrete_peer_refuses_old_channel_messages_and_discards_partial(endpoint):
    owner, channel, inbox = endpoint
    channel.fire('message', begin())
    channel.fire('message', b'half')
    owner._pc = FakePeerConnection()
    channel.fire('message', b'late')
    channel.fire('message', end())
    assert list(inbox.iterdir()) == []


def test_unauthenticated_viewer_refuses_incoming_file_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(webrtc_files, 'default_inbox_dir', lambda: tmp_path)
    viewer = WebRTCDesktopViewer(token='controlled')
    channel = Channel('files', ready_state='open')
    viewer._files_channel = channel
    viewer._wire_files_channel(channel)
    channel.fire('message', begin('unauthenticated.bin', 0))
    channel.fire('message', end())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('endpoint', ['host'], indirect=True)
def test_revoking_host_file_permission_aborts_without_waiting_for_more_messages(endpoint):
    owner, channel, inbox = endpoint
    channel.fire('message', begin())
    channel.fire('message', b'half')
    owner.set_permissions(SessionPermissions.none())
    assert list(inbox.iterdir()) == []


@pytest.mark.parametrize('state', ['failed', 'closed', 'disconnected', 'control_close'])
def test_connection_or_control_loss_discards_partial_without_another_file_frame(endpoint, state):
    owner, channel, inbox = endpoint
    channel.fire('message', begin())
    channel.fire('message', b'half')
    if state == 'control_close':
        control = Channel('ctrl')
        owner._control_channel = control
        owner._wire_control_channel(control)
        control.fire('close')
    else:
        pc = owner._pc
        if isinstance(owner, WebRTCDesktopHost):
            owner._wire_state_handlers(pc)
        else:
            owner._wire_pc_handlers(pc)
        pc.connectionState = state
        asyncio.run(pc.handlers['connectionstatechange']())
    assert not owner.authenticated and list(inbox.iterdir()) == []


def test_late_state_and_control_close_callbacks_do_not_revoke_a_new_connection(endpoint):
    owner, channel, inbox = endpoint
    old_pc = owner._pc
    if isinstance(owner, WebRTCDesktopHost):
        owner._wire_state_handlers(old_pc)
    else:
        owner._wire_pc_handlers(old_pc)
    old_control = Channel('ctrl')
    owner._control_channel = old_control
    owner._wire_control_channel(old_control)
    owner._pc = FakePeerConnection()
    owner._control_channel = Channel('ctrl')
    replacement = Channel('files')
    owner._wire_files_channel(replacement)
    replacement.fire('message', begin(size=4))
    replacement.fire('message', b'new!')
    old_pc.connectionState = 'closed'
    asyncio.run(old_pc.handlers['connectionstatechange']())
    old_control.fire('close')
    assert owner.authenticated
    replacement.fire('message', end())
    assert (inbox / 'payload.bin').read_bytes() == b'new!'


@pytest.mark.parametrize('boundary', ['write', 'close'])
@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, asyncio.CancelledError,
                                  CancelledError, OperationCancelledError])
def test_receive_cleanup_removes_partial_and_preserves_wrapped_control(tmp_path, signal, boundary):
    receiver = FileTransferReceiver(tmp_path)
    receiver.handle_message(begin())
    stream = receiver._current['fh']
    original = signal('controlled')

    class FailedStream:
        def write(self, chunk):
            if boundary == 'write':
                raise OSError('wrapped write') from original
            return stream.write(chunk)

        def close(self):
            stream.close()
            if boundary == 'close':
                raise OSError('wrapped close') from original

    receiver._current['fh'] = FailedStream()
    with pytest.raises(signal) as caught:
        if boundary == 'write':
            receiver.handle_message(b'half')
        else:
            receiver.close()
    assert caught.value is original and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, asyncio.CancelledError,
                                  CancelledError, OperationCancelledError])
def test_native_file_received_callback_preserves_wrapped_control_after_publication(endpoint, signal):
    owner, channel, inbox = endpoint
    original = signal('controlled')

    def failed(_path):
        raise RuntimeError('wrapped callback') from original

    owner.set_file_received_callback(failed)
    channel.fire('message', begin(size=4))
    channel.fire('message', b'done')
    with pytest.raises(signal) as caught:
        channel.fire('message', end())
    assert caught.value is original and (inbox / 'payload.bin').read_bytes() == b'done'
    assert list(inbox.glob('*.part')) == []


@pytest.mark.parametrize('endpoint', ['host'], indirect=True)
@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, asyncio.CancelledError,
                                  CancelledError, OperationCancelledError])
def test_native_file_audit_preserves_wrapped_control_after_publication(endpoint, signal, monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.utils.remote_desktop import webrtc_host

    owner, channel, inbox = endpoint
    original = signal('controlled')

    def failed(*_args, **_kwargs):
        raise OSError('wrapped audit') from original

    monkeypatch.setattr(webrtc_host, 'default_audit_log', lambda: SimpleNamespace(log=failed))
    channel.fire('message', begin(size=4))
    channel.fire('message', b'done')
    with pytest.raises(signal) as caught:
        channel.fire('message', end())
    assert caught.value is original and (inbox / 'payload.bin').read_bytes() == b'done'
    assert list(inbox.glob('*.part')) == []


def test_state_callback_can_attach_a_new_peer_without_old_failure_retiring_it(endpoint):
    owner, _channel, inbox = endpoint
    old_pc = owner._pc
    replacement = Channel('files')

    def reconnected(_state):
        owner._pc = FakePeerConnection()
        owner._authenticated = True
        owner._wire_files_channel(replacement)
        replacement.fire('message', begin(size=4))
        replacement.fire('message', b'new!')

    owner._on_state_change = reconnected
    if isinstance(owner, WebRTCDesktopHost):
        owner._wire_state_handlers(old_pc)
    else:
        owner._wire_pc_handlers(old_pc)
    old_pc.connectionState = 'failed'
    asyncio.run(old_pc.handlers['connectionstatechange']())
    assert owner.authenticated
    replacement.fire('message', end())
    assert (inbox / 'payload.bin').read_bytes() == b'new!'


@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, asyncio.CancelledError,
                                  CancelledError, OperationCancelledError])
def test_state_callback_control_survives_after_terminal_receive_cleanup(endpoint, signal):
    owner, channel, inbox = endpoint
    channel.fire('message', begin())
    channel.fire('message', b'half')
    original = signal('controlled')

    def failed(_state):
        raise RuntimeError('wrapped state callback') from original

    owner._on_state_change = failed
    pc = owner._pc
    if isinstance(owner, WebRTCDesktopHost):
        owner._wire_state_handlers(pc)
    else:
        owner._wire_pc_handlers(pc)
    pc.connectionState = 'failed'

    async def observe_native_callback():
        # Observe before Python 3.10 Task.result replaces a propagated CancelledError object.
        with pytest.raises(signal) as caught:
            await pc.handlers['connectionstatechange']()
        return caught.value

    caught = asyncio.run(observe_native_callback())
    assert caught is original and not owner.authenticated and list(inbox.iterdir()) == []


@pytest.mark.parametrize('endpoint', ['host'], indirect=True)
def test_granting_files_again_uses_a_new_transfer_without_reviving_old_partial_bytes(endpoint):
    owner, channel, inbox = endpoint
    channel.fire('message', begin('old.bin'))
    channel.fire('message', b'old')
    owner.set_permissions(SessionPermissions.none())
    owner.set_permissions(SessionPermissions.full_control())
    channel.fire('message', begin('new.bin', 4))
    channel.fire('message', b'new!')
    channel.fire('message', end())
    assert sorted(p.name for p in inbox.iterdir()) == ['new.bin']
    assert (inbox / 'new.bin').read_bytes() == b'new!'
