"""Queued DataChannel failures must reach synchronous file callers and folder retry state."""
import asyncio
import json
from concurrent.futures import CancelledError
from pathlib import Path
from threading import Event, Thread

import pytest

from headless.test_folder_sync_content import loop
from je_auto_control.utils.remote_desktop import webrtc_files
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.remote_desktop.webrtc_files import (
    FileTransferError, FileTransferReceiver, FileTransferSender,
)
from je_auto_control.utils.remote_desktop.webrtc_transport import _AsyncioBridge


@pytest.fixture
def bridge(monkeypatch):
    active = _AsyncioBridge()
    failures = []
    active.start().call_soon_threadsafe(
        active._loop.set_exception_handler, lambda _loop, context: failures.append(context))
    monkeypatch.setattr(webrtc_files, 'get_bridge', lambda: active)
    yield active, failures
    active.stop()


def test_caller_waits_for_the_channel_callback_and_receives_its_failure(bridge, tmp_path):
    active, failures = bridge
    entered, release, finished = Event(), Event(), Event()
    caught = []
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'payload')

    class ClosedChannel:
        def send(self, _message):
            entered.set()
            assert release.wait(5)
            raise RuntimeError('controlled closed channel')

    def send():
        try:
            FileTransferSender(ClosedChannel()).send(source)
        except Exception as error:
            caught.append(error)
        finally:
            finished.set()

    worker = Thread(target=send)
    worker.start()
    try:
        assert entered.wait(5)
        assert not finished.wait(.1), 'queued callbacks were incorrectly reported as delivered'
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert len(caught) == 1 and isinstance(caught[0], FileTransferError)
    active.submit(asyncio.sleep(0)).result(5)
    assert failures == [], 'channel exceptions escaped onto the event loop instead of reaching the sender'


def test_folder_retry_survives_a_failure_that_occurs_on_the_bridge_thread(bridge, tmp_path):
    active, failures = bridge
    watch = tmp_path / 'watch'
    watch.mkdir()
    target = watch / 'retry.bin'
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    connected = False
    done = []

    class Channel:
        def send(self, message):
            if not connected:
                raise RuntimeError('controlled disconnect')
            receiver.handle_message(message, on_done=done.append)

    sender = FileTransferSender(Channel())
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda path, name: sender.send(path, remote_name=name))

    def reconnect():
        nonlocal connected
        active.submit(asyncio.sleep(0)).result(5)
        connected = True

    loop(engine, lambda: target.write_bytes(b'pending'), reconnect, lambda: None)
    active.submit(asyncio.sleep(0)).result(5)
    assert done and done[0].read_bytes() == b'pending'
    assert failures == []


@pytest.mark.parametrize('chunk_size', [0, -1, True, 1.5, 1024 * 1024 + 1])
def test_invalid_chunk_sizes_are_rejected_before_opening_a_channel(bridge, tmp_path, chunk_size):
    active, _ = bridge
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'payload')
    messages = []

    class Channel:
        def send(self, message):
            messages.append(message)

    with pytest.raises(FileTransferError, match='chunk'):
        FileTransferSender(Channel()).send(source, chunk_size=chunk_size)
    active.submit(asyncio.sleep(0)).result(5)
    assert messages == []


def test_prestart_cancel_never_reads_the_selected_file(bridge, tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('prestart cancellation accessed the source')

    class Channel:
        def send(self, _message):
            pytest.fail('prestart cancellation wrote the channel')

    monkeypatch.setattr(Path, 'is_file', forbidden)
    with pytest.raises(CancelledError):
        FileTransferSender(Channel()).send(tmp_path / 'missing', cancelled=lambda: True)


def test_mid_file_cancel_aborts_partial_bytes_and_preserves_the_existing_target(bridge, tmp_path):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'0123456789')
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    target = tmp_path / 'inbox' / 'payload.bin'
    target.write_bytes(b'previous target')
    cancelled = Event()
    progress = []

    class Channel:
        def send(self, message):
            receiver.handle_message(message)

    def accepted(sent, _total):
        progress.append(sent)
        cancelled.set()

    with pytest.raises(CancelledError):
        FileTransferSender(Channel()).send(source, chunk_size=4, on_progress=accepted, cancelled=cancelled.is_set)
    assert progress == [4]
    assert target.read_bytes() == b'previous target'
    assert sorted(path.name for path in target.parent.iterdir()) == ['payload.bin']


def test_send_from_the_bridge_thread_does_not_deadlock(bridge, tmp_path):
    active, failures = bridge
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'data')
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    done = []

    class Channel:
        def send(self, message):
            receiver.handle_message(message, on_done=done.append)

    async def send():
        FileTransferSender(Channel()).send(source)

    active.submit(send()).result(5)
    assert done[0].read_bytes() == b'data' and failures == []


def test_a_full_channel_buffer_waits_until_the_loop_drains_it(bridge, tmp_path):
    active, failures = bridge
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'data')
    messages = []

    class Channel:
        bufferedAmount = 1024 * 1024
        readyState = 'open'

        def send(self, message):
            messages.append(message)

    channel = Channel()

    async def drain():
        await asyncio.sleep(.01)
        channel.bufferedAmount = 0

    active.submit(drain())
    FileTransferSender(channel).send(source)
    assert b'data' in messages and failures == []


@pytest.mark.parametrize('signal', [CancelledError('cancel'), KeyboardInterrupt(), SystemExit(8)])
def test_wrapped_channel_signals_reach_the_caller_by_identity(bridge, tmp_path, signal):
    active, failures = bridge
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'data')

    class Channel:
        def send(self, _message):
            raise RuntimeError('controlled channel carrier') from signal

    with pytest.raises(type(signal)) as caught:
        FileTransferSender(Channel()).send(source)
    assert caught.value is signal
    active.submit(asyncio.sleep(0)).result(5)
    assert failures == []


def test_cancelled_cleanup_retains_the_channel_until_its_late_abort_executes(bridge, tmp_path):
    active, failures = bridge
    entered, release, cancelled, finished = Event(), Event(), Event(), Event()
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'abcdefgh')
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    completed = []
    caught = []

    def block():
        entered.set()
        assert release.wait(5)

    class Channel:
        blocked = False

        def send(self, message):
            receiver.handle_message(message, on_done=completed.append)
            if isinstance(message, bytes) and not self.blocked:
                self.blocked = True
                active._loop.call_soon(block)

    channel = Channel()

    def send():
        try:
            FileTransferSender(channel).send(source, chunk_size=4, cancelled=cancelled.is_set)
        except Exception as error:
            caught.append(error)
        finally:
            finished.set()

    worker = Thread(target=send)
    worker.start()
    replacement_finished = Event()
    replacement_errors = []

    def replace():
        try:
            FileTransferSender(channel).send(source)
        except FileTransferError as error:
            replacement_errors.append(error)
        finally:
            replacement_finished.set()

    replacement = Thread(target=replace)
    try:
        assert entered.wait(5)
        cancelled.set()
        assert finished.wait(3)
        assert len(caught) == 1 and isinstance(caught[0], CancelledError)
        replacement.start()
        assert replacement_finished.wait(.1), 'a new transfer overlapped a pending abort'
        assert len(replacement_errors) == 1
    finally:
        release.set()
        worker.join(5)
        if replacement.ident is not None:
            replacement.join(5)
    active.submit(asyncio.sleep(0)).result(5)
    assert completed == [] and list((tmp_path / 'inbox').iterdir()) == []
    FileTransferSender(channel).send(source)
    assert completed[0].read_bytes() == b'abcdefgh' and failures == []


def test_stop_after_confirmed_end_does_not_turn_a_completed_send_into_cancellation(tmp_path, monkeypatch):
    cancelled = Event()
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'complete bytes')
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    done = []

    class Bridge:
        def call_soon(self, callback, *args):
            callback(*args)

    class Channel:
        def send(self, message):
            receiver.handle_message(message, on_done=done.append)
            if isinstance(message, str) and json.loads(message)['type'] == 'file_end':
                cancelled.set()

    monkeypatch.setattr(webrtc_files, 'get_bridge', Bridge)
    FileTransferSender(Channel()).send(source, cancelled=cancelled.is_set)
    assert done[0].read_bytes() == b'complete bytes'


def test_cancellation_is_checked_when_a_queued_data_write_actually_executes(tmp_path, monkeypatch):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'abcdefgh')
    cancelled = Event()
    messages = []

    class Bridge:
        count = 0

        def call_soon(self, callback, *args):
            self.count += 1
            if self.count == 2:
                cancelled.set()
            callback(*args)

    class Channel:
        def send(self, message):
            messages.append(message)

    scheduler = Bridge()
    monkeypatch.setattr(webrtc_files, 'get_bridge', lambda: scheduler)
    with pytest.raises(CancelledError):
        FileTransferSender(Channel()).send(source, chunk_size=4, cancelled=cancelled.is_set)
    assert not any(isinstance(message, bytes) for message in messages)


def test_replaced_bridge_epoch_cannot_receive_later_chunks_or_cleanup(tmp_path, monkeypatch):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'abcdefgh')
    messages = []

    class Bridge:
        _loop = object()

        def call_soon(self, callback, *args):
            callback(*args)
            self._loop = object()

    class Channel:
        def send(self, message):
            messages.append(message)

    scheduler = Bridge()
    monkeypatch.setattr(webrtc_files, 'get_bridge', lambda: scheduler)
    with pytest.raises(FileTransferError):
        FileTransferSender(Channel()).send(source, chunk_size=4)
    assert len(messages) == 1 and json.loads(messages[0])['type'] == 'file_begin'


def test_large_inbox_request_yields_to_the_bridge_while_its_file_buffer_drains(bridge, tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop import webrtc_host

    active, failures = bridge
    monkeypatch.setattr(webrtc_host, 'get_bridge', lambda: active)
    host = webrtc_host.WebRTCDesktopHost(token='controlled', inbox_dir=tmp_path / 'source')
    host._authenticated = True
    host._closed.clear()
    source = host._ensure_files_receiver()._inbox / 'large.bin'
    source.write_bytes(bytes(range(256)) * 8192)
    receiver = FileTransferReceiver(tmp_path / 'receiver')
    completed = Event()

    class Channel:
        readyState = 'open'
        bufferedAmount = 0

        def send(self, message):
            self.bufferedAmount += len(message)
            receiver.handle_message(message, on_done=lambda _path: completed.set())
            active._loop.call_soon(self.drained)

        def drained(self):
            self.bufferedAmount = 0

    host._files_channel = Channel()

    async def request():
        host._handle_request_file({'name': 'large.bin'})

    async def finish():
        if host._background_tasks:
            await asyncio.gather(*tuple(host._background_tasks))

    active.submit(request()).result(5)
    try:
        assert completed.wait(3), 'the inbox request blocked its own loop and could not drain the buffer'
        active.submit(finish()).result(5)
        assert (tmp_path / 'receiver' / 'large.bin').read_bytes() == source.read_bytes()
        assert failures == []
    finally:
        active.submit(host._async_stop()).result(5)


@pytest.mark.parametrize('changed', [b'x', b'abcdefghijkl'])
def test_a_source_that_changes_size_does_not_report_success_or_replace_the_target(bridge, tmp_path,
                                                                                monkeypatch, changed):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'abcdefgh')
    receiver = FileTransferReceiver(tmp_path / 'inbox')
    target = tmp_path / 'inbox' / 'payload.bin'
    target.write_bytes(b'previous target')
    done = []
    original_open = Path.open

    def unbuffered(path, *args, **kwargs):
        if path == source and args and args[0] == 'rb':
            kwargs['buffering'] = 0
        return original_open(path, *args, **kwargs)

    def edited(sent, _total):
        if sent == 4:
            source.write_bytes(changed)

    class Channel:
        def send(self, message):
            receiver.handle_message(message, on_done=done.append)

    monkeypatch.setattr(Path, 'open', unbuffered)
    with pytest.raises(FileTransferError, match='size changed'):
        FileTransferSender(Channel()).send(source, chunk_size=4, on_progress=edited)
    assert done == [] and target.read_bytes() == b'previous target'
    assert sorted(path.name for path in target.parent.iterdir()) == ['payload.bin']


@pytest.mark.parametrize('state', ['connecting', 'closing', 'closed'])
def test_a_channel_without_an_open_state_is_refused_before_any_message(bridge, tmp_path, state):
    source = tmp_path / 'payload.bin'
    source.write_bytes(b'data')
    messages = []

    class Channel:
        readyState = state

        def send(self, message):
            messages.append(message)

    with pytest.raises(FileTransferError, match='not open'):
        FileTransferSender(Channel()).send(source)
    assert messages == []


def test_stopping_a_host_cancels_and_awaits_its_pending_file_request_job(bridge, tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop import webrtc_host

    active, failures = bridge
    monkeypatch.setattr(webrtc_host, 'get_bridge', lambda: active)
    host = webrtc_host.WebRTCDesktopHost(token='controlled', inbox_dir=tmp_path / 'source')
    host._authenticated = True
    source = host._ensure_files_receiver()._inbox / 'payload.bin'
    source.write_bytes(b'pending bytes')
    attempted, exited = Event(), Event()
    sent = []
    original_push = host.push_file

    class Channel:
        readyState = 'open'

        @property
        def bufferedAmount(self):
            attempted.set()
            return 1024 * 1024

        def send(self, message):
            sent.append(message)

    channel = Channel()
    host._files_channel = channel

    class Connection:
        async def close(self):
            channel.readyState = 'closed'

    host._pc = Connection()

    def tracked_push(*args, **kwargs):
        try:
            return original_push(*args, **kwargs)
        finally:
            exited.set()

    monkeypatch.setattr(host, 'push_file', tracked_push)

    async def request():
        host._handle_request_file({'name': 'payload.bin'})

    active.submit(request()).result(5)
    assert attempted.wait(5)
    active.submit(host._async_stop()).result(5)
    assert exited.wait(3)
    active.submit(asyncio.sleep(0)).result(5)
    assert host._closed.is_set() and not host._background_tasks
    assert host._files_channel is None and not host.authenticated
    assert not any(isinstance(message, bytes) for message in sent)
    assert failures == []


def test_two_inbox_requests_queue_without_interleaving_or_losing_the_second_file(bridge, tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop import webrtc_host

    active, failures = bridge
    monkeypatch.setattr(webrtc_host, 'get_bridge', lambda: active)
    host = webrtc_host.WebRTCDesktopHost(token='controlled', inbox_dir=tmp_path / 'source')
    host._authenticated = True
    inbox = host._ensure_files_receiver()._inbox
    (inbox / 'one.bin').write_bytes(b'first file')
    (inbox / 'two.bin').write_bytes(b'second file')
    receiver = FileTransferReceiver(tmp_path / 'receiver')
    attempted, completed, refused = Event(), Event(), Event()
    names = []

    class Channel:
        readyState = 'open'
        full = True

        @property
        def bufferedAmount(self):
            attempted.set()
            return 1024 * 1024 if self.full else 0

        def send(self, message):
            receiver.handle_message(message, on_done=received)

    class Control:
        def send(self, message):
            if json.loads(message).get('ok') is False:
                refused.set()

    def received(path):
        names.append(path.name)
        if len(names) == 2:
            completed.set()

    channel = Channel()
    host._files_channel = channel
    host._control_channel = Control()

    async def request(name):
        host._handle_request_file({'name': name})

    async def finish():
        if host._background_tasks:
            await asyncio.gather(*tuple(host._background_tasks))

    try:
        active.submit(request('one.bin')).result(5)
        assert attempted.wait(5)
        active.submit(request('two.bin')).result(5)
        assert not refused.wait(.2), 'a normal multi-file download was rejected as concurrent'
        channel.full = False
        assert completed.wait(5)
        active.submit(finish()).result(5)
        assert names == ['one.bin', 'two.bin'] and failures == []
    finally:
        channel.full = False
        active.submit(host._async_stop()).result(5)


def test_inbox_queue_bounds_and_cancellation_before_start_release_capacity(monkeypatch):
    from je_auto_control.utils.remote_desktop import webrtc_file_tasks as tasks

    monkeypatch.setattr(tasks, '_MAX_REQUESTS', 2)
    sent, failures, owned = [], [], set()
    channel = object()

    def sender(path, remote_name=None, *, cancelled=None):
        sent.append((path, remote_name))

    async def scenario():
        for name in ('one', 'two', 'overflow'):
            tasks.start_file_request(owned, sender, name, name, channel, lambda: True, failures.append)
        assert len(owned) == 2 and len(failures) == 1 and 'queue is full' in failures[0]
        await tasks.cancel_file_requests(owned)
        await asyncio.sleep(0)
        assert not owned and sent == []
        tasks.start_file_request(owned, sender, 'fresh', 'fresh', channel, lambda: True, failures.append)
        await asyncio.gather(*tuple(owned))
        await asyncio.sleep(0)
        assert not owned and sent == [('fresh', 'fresh')]

    asyncio.run(scenario())


def test_inbox_failure_reply_stays_on_the_original_active_control_channel():
    from je_auto_control.utils.remote_desktop.webrtc_file_tasks import file_request_failure

    messages, active = [], True

    class Channel:
        def send(self, message):
            messages.append(json.loads(message))

    reply = file_request_failure(Channel(), 'one.bin', lambda: active)
    reply('controlled')
    active = False
    reply('stale')
    assert messages == [{'type': 'request_file_response', 'name': 'one.bin', 'ok': False, 'error': 'controlled'}]


@pytest.mark.parametrize('signal', [KeyboardInterrupt, SystemExit, CancelledError])
def test_inbox_failure_reply_preserves_wrapped_controls(signal):
    from je_auto_control.utils.remote_desktop.webrtc_file_tasks import file_request_failure

    original = signal('controlled')

    class Channel:
        def send(self, _message):
            raise RuntimeError('wrapped') from original

    with pytest.raises(signal) as caught:
        file_request_failure(Channel(), 'one.bin', lambda: True)('failed')
    assert caught.value is original
