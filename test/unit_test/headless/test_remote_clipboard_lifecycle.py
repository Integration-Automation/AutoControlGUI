"""A buffered clipboard message cannot outlive its connection, permissions or original control signals."""
import asyncio
from concurrent.futures import CancelledError
from threading import Condition, Event, Thread
from types import SimpleNamespace

import pytest

from je_auto_control.utils.exception.control_signals import OperationCancelledError
from je_auto_control.utils.remote_desktop.clipboard_sync import encode_image, encode_text
from je_auto_control.utils.remote_desktop.host_client import _ClientHandler
from je_auto_control.utils.remote_desktop.host_access import PERMISSION_VIEW_ONLY, PERMISSION_DENIED
from je_auto_control.utils.remote_desktop.protocol import MessageType
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop import viewer as viewer_module
from je_auto_control.utils.remote_desktop.ws_viewer import WebSocketDesktopViewer
from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop import host_client as host_module


class BufferedChannel:
    def __init__(self, payload):
        self.entered, self.release = Event(), Event()
        self.payload = payload
        self.closed = False

    def read_typed(self):
        self.entered.set()
        assert self.release.wait(5)
        return MessageType.CLIPBOARD, self.payload

    def close(self):
        self.closed = True


@pytest.mark.parametrize('payload', [encode_text('old text'), encode_image(b'old image')], ids=['text', 'image'])
@pytest.mark.parametrize('replacement', [False, True])
def test_buffered_old_viewer_clipboard_is_rejected_after_disconnect_or_reconnect(payload, replacement):
    applied, results = [], []
    viewer = RemoteDesktopViewer('127.0.0.1', 1, 'controlled', on_clipboard=lambda *args: applied.append(args))
    channel = BufferedChannel(payload)
    viewer._channel, viewer._connected = channel, True
    worker = Thread(target=lambda: results.append(viewer._read_and_dispatch(channel)))
    worker.start()
    try:
        assert channel.entered.wait(5)
        viewer.disconnect(timeout=0)
        if replacement:
            viewer._channel, viewer._connected, viewer._shutdown = object(), True, Event()
    finally:
        channel.release.set()
        worker.join(5)
    assert not worker.is_alive() and channel.closed
    assert applied == [], 'old buffered clipboard reached the replacement/current callback'
    assert results == [False] and viewer.connected is replacement


def host_handler(payload, applied):
    host = SimpleNamespace(_file_receiver=None, _frame_cond=Condition(),
                           _apply_clipboard=lambda *args: applied.append(args))
    handler = _ClientHandler(host, BufferedChannel(payload), ('127.0.0.1', 1))
    handler.authenticated = True
    return handler


@pytest.mark.parametrize('revoked', ['stop', 'authentication', PERMISSION_VIEW_ONLY, PERMISSION_DENIED, 'invalid'])
def test_host_rechecks_stop_authentication_and_control_permission_after_a_buffered_read(revoked):
    applied = []
    handler = host_handler(encode_text('late text'), applied)
    channel = handler._channel
    worker = Thread(target=handler._recv_loop)
    worker.start()
    try:
        assert channel.entered.wait(5)
        if revoked == 'stop':
            handler.stop()
        elif revoked == 'authentication':
            handler.authenticated = False
        else:
            handler.permission = revoked
        # The first read is already entered, so stop on its next read instead.
        channel.read_typed = lambda: (_ for _ in ()).throw(OSError('finished'))
    finally:
        channel.release.set()
        worker.join(5)
        handler.stop()
    assert not worker.is_alive()
    assert applied == [], 'a stopped or unprivileged client still set the host clipboard'


def controls():
    return [KeyboardInterrupt(), SystemExit(3), GeneratorExit(), asyncio.CancelledError(), CancelledError(),
            OperationCancelledError('clipboard')]


@pytest.mark.parametrize('original', controls(), ids=lambda value: type(value).__name__)
@pytest.mark.parametrize('boundary', ['viewer', 'host'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_clipboard_callback_boundaries_preserve_wrapped_original_control_objects(original, boundary, wrapped):
    def interrupted(*_args):
        if not wrapped:
            raise original
        error = RuntimeError('callback wrapper')
        error.__cause__ = original
        raise error

    if boundary == 'viewer':
        receiver = RemoteDesktopViewer('127.0.0.1', 1, 'controlled', on_clipboard=interrupted)
    else:
        receiver = host_handler(encode_text('text'), [])
        receiver._host._apply_clipboard = interrupted
    with pytest.raises(type(original)) as caught:
        receiver._handle_clipboard_payload(encode_text('text'))
    assert caught.value is original


@pytest.mark.parametrize('kind,value', [('text', 'captured text'), ('image', b'captured image')])
@pytest.mark.parametrize('transport', [RemoteDesktopViewer, WebSocketDesktopViewer], ids=['tcp', 'ws'])
def test_clipboard_send_does_not_migrate_to_a_replacement_channel_during_encoding(monkeypatch, kind, value, transport):
    old, new = [], []
    viewer = transport('127.0.0.1', 1, 'controlled')
    channel = SimpleNamespace(send_typed=lambda *args: old.append(args))
    viewer._channel, viewer._connected = channel, True
    encode = getattr(viewer_module, 'encode_' + kind)

    def replaced(data):
        viewer._channel = SimpleNamespace(send_typed=lambda *args: new.append(args))
        return encode(data)

    monkeypatch.setattr(viewer_module, 'encode_' + kind, replaced)
    with pytest.raises(ConnectionError):
        getattr(viewer, 'send_clipboard_' + kind)(value)
    assert old == [] and new == [], 'a clipboard send adopted the replacement transport'


@pytest.mark.parametrize('kind,value', [('text', 'text'), ('image', b'image')])
def test_viewer_rechecks_its_original_channel_after_decoding(monkeypatch, kind, value):
    applied = []
    viewer = RemoteDesktopViewer('127.0.0.1', 1, 'controlled', on_clipboard=lambda *args: applied.append(args))
    channel = BufferedChannel(encode_text('text'))
    channel.release.set()
    viewer._channel, viewer._connected = channel, True

    def decode(_payload):
        viewer._channel = object()
        return kind, value

    monkeypatch.setattr(viewer_module, 'decode_clipboard', decode)
    viewer._read_and_dispatch(channel)
    assert applied == []


@pytest.mark.parametrize('revoked', ['stop', 'authentication', PERMISSION_VIEW_ONLY])
def test_host_rechecks_revocation_after_clipboard_decoding(monkeypatch, revoked):
    applied = []
    handler = host_handler(encode_text('text'), applied)

    def decode(_payload):
        if revoked == 'stop':
            handler.stop()
        elif revoked == 'authentication':
            handler.authenticated = False
        else:
            handler.permission = revoked
        return 'text', 'late decoded value'

    monkeypatch.setattr(host_module, 'decode_clipboard', decode)
    handler._handle_clipboard_payload(encode_text('text'))
    assert applied == []


@pytest.mark.parametrize('transport', [RemoteDesktopViewer, WebSocketDesktopViewer], ids=['tcp', 'ws'])
@pytest.mark.parametrize('kind,value', [('text', 'same value'), ('image', b'same image')])
def test_explicit_two_viewer_broadcasts_do_not_echo_or_discard_deliberate_repeats(transport, kind, value):
    host = RemoteDesktopHost(token='controlled', host_id='123456789', frame_provider=lambda: b'frame',
                             input_dispatcher=lambda *_args: None, enable_cursor_broadcast=False)
    applied = []
    host._apply_clipboard = lambda *args: applied.append(args)

    def peer():
        received, outgoing, incoming = [], [], []
        viewer = transport('127.0.0.1', 1, 'controlled', on_clipboard=lambda *args: received.append(args))
        handler = _ClientHandler(host, None, ('127.0.0.1', 1))

        def send(kind, payload):
            outgoing.append((kind, payload))
            assert len(outgoing) < 10, 'clipboard reflection loop'
            handler._route_incoming(kind, payload)

        def broadcast(kind, payload):
            incoming.append((kind, payload))
            assert len(incoming) < 10, 'clipboard reflection loop'
            viewer._handle_clipboard_payload(payload, viewer._channel)

        viewer._channel = SimpleNamespace(send_typed=send)
        viewer._connected = True
        handler._channel = SimpleNamespace(send_typed=broadcast)
        handler.authenticated = True
        host._clients.append(handler)
        return viewer, received, outgoing, incoming

    first, second = peer(), peer()
    for _ in range(2):
        getattr(first[0], 'send_clipboard_' + kind)(value)
    assert applied == [(kind, value)] * 2
    assert first[1] == second[1] == []
    for _ in range(2):
        assert getattr(host, 'broadcast_clipboard_' + kind)(value) == 2
    assert first[1] == second[1] == [(kind, value)] * 2
    assert applied == [(kind, value)] * 2 and len(first[2]) == 2 and second[2] == []
    assert len(first[3]) == len(second[3]) == 2


@pytest.mark.parametrize('boundary', ['viewer', 'host'])
@pytest.mark.parametrize('error', [RuntimeError('ordinary callback'), OSError('ordinary provider')])
def test_ordinary_clipboard_callback_failures_remain_logged_and_contained(boundary, error, caplog):
    def failed(*_args):
        raise error

    if boundary == 'viewer':
        receiver = RemoteDesktopViewer('127.0.0.1', 1, 'controlled', on_clipboard=failed)
    else:
        receiver = host_handler(encode_text('text'), [])
        receiver._host._apply_clipboard = failed
    receiver._handle_clipboard_payload(encode_text('text'))
    assert 'clipboard' in caplog.text and str(error) in caplog.text
