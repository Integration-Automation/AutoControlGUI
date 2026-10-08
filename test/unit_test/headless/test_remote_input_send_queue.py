"""A viewer's ``send_input`` never waits for the socket (no Qt, fake channels, one local socket pair).

It used to write on the caller's thread -- the GUI thread, once per mouse
move -- so a host that stopped reading froze the viewer's window.
"""
import json
import socket
import threading
import time

import pytest

from je_auto_control.utils.remote_desktop.input_send_queue import (
    InputSendQueue, set_send_timeout,
)
from je_auto_control.utils.remote_desktop.protocol import MessageType
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.remote_desktop.ws_viewer import WebSocketDesktopViewer

_PROMPT_S = 5.0
_WAIT_S = 10.0


def _wait(predicate, timeout=_WAIT_S):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    return predicate()


class _Sink:
    """What the writer calls: records payloads, and can hold a write until let go."""

    def __init__(self, blocked=False):
        self.sent, self.threads, self.error = [], [], None
        self.entered, self.release = threading.Event(), threading.Event()
        if not blocked:
            self.release.set()

    def __call__(self, payload):
        self.threads.append(threading.current_thread())
        self.entered.set()
        self.release.wait(30.0)
        if self.error is not None:
            raise self.error
        self.sent.append(json.loads(payload))


def _move(index):
    return {"action": "mouse_move", "x": index, "y": index}


def _key(index):
    return {"action": "key_press", "keycode": index}


@pytest.fixture()
def errors():
    return []


def _queue(sink, errors, **options):
    return InputSendQueue(sink, errors.append, **options)


def test_events_are_written_in_order_by_another_thread(errors):
    sink = _Sink()
    queue = _queue(sink, errors)
    events = [_move(1), _key(2), {"action": "mouse_press", "button": "left"}, _move(3)]
    for event in events:
        queue.put(event)
    assert _wait(lambda: len(sink.sent) == 4)
    assert sink.sent == events and errors == []
    assert all(thread is not threading.current_thread() for thread in sink.threads)
    queue.close()


def test_put_returns_while_a_write_is_stuck(errors):
    sink = _Sink(blocked=True)
    queue = _queue(sink, errors)
    started = time.monotonic()
    for index in range(50):
        queue.put(_key(index))
    assert time.monotonic() - started < _PROMPT_S
    assert sink.entered.wait(_WAIT_S) and sink.sent == []
    sink.release.set()
    assert _wait(lambda: len(sink.sent) == 50)
    queue.close()


def test_stale_moves_give_way_and_keys_and_buttons_never_do(errors):
    sink = _Sink(blocked=True)
    queue = _queue(sink, errors, limit=8)
    queue.put(_key(0))                          # taken by the writer, which then blocks
    assert sink.entered.wait(_WAIT_S)
    kept = []
    for index in range(1, 100):             # 24 keys: under the hard limit of 32
        event = _move(index) if index % 4 else _key(index)
        if event["action"] == "key_press":
            kept.append(event)
        queue.put(event)
    queue.put(_move(1000))
    assert queue.dropped_moves > 0
    sink.release.set()
    assert _wait(lambda: queue.pending == 0 and len(sink.sent) >= len(kept) + 1)
    sent_keys = [event for event in sink.sent if event["action"] == "key_press"]
    assert sent_keys == [_key(0), *kept], "a key or button event was dropped or reordered"
    moves = [event["x"] for event in sink.sent if event["action"] == "mouse_move"]
    assert moves == sorted(moves) and len(moves) + queue.dropped_moves == 76
    assert errors == []
    queue.close()


def test_the_newest_move_survives_when_older_moves_are_queued(errors):
    sink = _Sink(blocked=True)
    queue = _queue(sink, errors, limit=4)
    queue.put(_key(0))
    assert sink.entered.wait(_WAIT_S)
    for index in range(1, 30):
        queue.put(_move(index))
    assert queue.pending == 4 and queue.dropped_moves == 25
    sink.release.set()
    assert _wait(lambda: len(sink.sent) == 5)
    assert sink.sent[-1] == _move(29), "the position the pointer ended on must be the last one sent"
    queue.close()


def test_a_move_named_by_type_is_droppable_too(errors):
    sink = _Sink(blocked=True)
    queue = _queue(sink, errors, limit=2)
    queue.put(_key(0))
    assert sink.entered.wait(_WAIT_S)
    for index in range(10):
        queue.put({"type": "mouse_move", "x": index, "y": 0})
    assert queue.pending == 2 and queue.dropped_moves == 8
    sink.release.set()
    queue.close()


def test_a_write_error_goes_to_on_error_once_and_the_queue_refuses_more(errors):
    sink = _Sink()
    sink.error = OSError("connection reset")
    queue = _queue(sink, errors)
    queue.put(_key(1))
    assert _wait(lambda: len(errors) == 1)
    assert errors == [sink.error] and queue.closed
    with pytest.raises(ConnectionError):
        queue.put(_key(2))
    assert errors == [sink.error]
    queue.close()


def test_a_write_out_too_long_is_reported_as_a_timeout_and_the_socket_is_let_go(errors):
    sink = _Sink(blocked=True)
    aborted = []
    queue = _queue(sink, errors, abort=lambda: (aborted.append(True), sink.release.set()),
                   stall_timeout_s=0.05)
    queue.put(_key(1))
    assert sink.entered.wait(_WAIT_S)
    time.sleep(0.2)
    started = time.monotonic()
    queue.put(_key(2))                          # the caller notices; it does not wait
    assert time.monotonic() - started < _PROMPT_S
    assert len(errors) == 1 and isinstance(errors[0], TimeoutError) and aborted == [True]
    with pytest.raises(ConnectionError):
        queue.put(_key(3))
    queue.close()


def test_keys_piling_up_far_past_the_limit_fail_the_connection_instead_of_being_dropped(errors):
    sink = _Sink(blocked=True)
    queue = _queue(sink, errors, limit=4, hard_factor=2)
    queue.put(_key(0))
    assert sink.entered.wait(_WAIT_S)
    for index in range(1, 9):
        queue.put(_key(index))                  # 8 waiting: at the hard limit, none dropped
    assert queue.pending == 8 and errors == []
    queue.put(_key(9))
    assert len(errors) == 1 and isinstance(errors[0], ConnectionError) and queue.closed
    sink.release.set()
    queue.close()


def test_close_stops_the_writer_and_is_safe_twice(errors):
    sink = _Sink()
    queue = _queue(sink, errors)
    queue.close()
    queue.close()
    assert not queue._thread.is_alive()
    with pytest.raises(ConnectionError):
        queue.put(_key(1))


def test_a_send_timeout_bounds_a_write_nobody_reads_and_leaves_reads_alone():
    left, right = socket.socketpair()
    try:
        assert set_send_timeout(left, 0.3)
        assert left.gettimeout() is None        # the receive side still blocks without a timeout
        started = time.monotonic()
        with pytest.raises(OSError):
            for _ in range(4096):
                left.sendall(b"x" * 65536)      # the peer never reads
        assert time.monotonic() - started < 30.0
    finally:
        left.close()
        right.close()


# --- the viewers ------------------------------------------------------------------------------------------------

class _Channel:
    sock = None

    def __init__(self, blocked=False):
        self.sink = _Sink(blocked)
        self.closed = False

    def send_typed(self, message_type, payload):
        assert message_type is MessageType.INPUT
        self.sink(payload)

    def close(self):
        self.closed = True
        self.sink.release.set()


@pytest.fixture(params=[RemoteDesktopViewer, WebSocketDesktopViewer], ids=["tcp", "websocket"])
def connected(request, errors):
    viewer = request.param("desk", 1, "tok", on_error=errors.append)
    channel = _Channel(blocked=True)
    viewer._channel, viewer._connected = channel, True
    viewer._start_input_queue(channel)
    yield viewer, channel
    viewer.disconnect()


def test_send_input_does_not_wait_for_a_host_that_stopped_reading(connected, errors):
    viewer, channel = connected
    started = time.monotonic()
    for index in range(2000):
        viewer.send_input(_move(index))
    viewer.send_input(_key(1))
    assert time.monotonic() - started < _PROMPT_S
    assert channel.sink.entered.wait(_WAIT_S) and channel.sink.sent == []
    backlog = viewer.input_backlog()
    assert backlog["pending"] <= viewer.INPUT_QUEUE_LIMIT and backlog["dropped_moves"] > 0
    channel.sink.release.set()
    assert _wait(lambda: viewer.input_backlog()["pending"] == 0 and channel.sink.sent[-1:] == [_key(1)])
    assert errors == []


def test_a_failed_write_reaches_on_error_and_the_viewer_reads_as_down(connected, errors):
    viewer, channel = connected
    channel.sink.error = OSError("broken pipe")
    viewer.send_input(_key(1))
    channel.sink.release.set()
    assert _wait(lambda: len(errors) == 1)
    assert errors == [channel.sink.error] and not viewer.connected
    with pytest.raises(ConnectionError):
        viewer.send_input(_key(2))


def test_send_input_still_validates_and_refuses_when_not_connected(connected):
    viewer, _channel = connected
    with pytest.raises(TypeError):
        viewer.send_input(["not", "a", "mapping"])
    viewer.disconnect()
    assert viewer.input_backlog() == {"pending": 0, "dropped_moves": 0}
    with pytest.raises(ConnectionError):
        viewer.send_input(_key(1))


def test_disconnect_ends_the_writer_even_with_a_write_in_the_socket(connected):
    viewer, channel = connected
    viewer.send_input(_key(1))
    assert channel.sink.entered.wait(_WAIT_S)
    queue = viewer._input_queue
    viewer.disconnect()
    assert channel.closed and _wait(lambda: not queue._thread.is_alive())
