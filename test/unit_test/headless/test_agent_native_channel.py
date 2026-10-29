"""Owned subprocess protocol tests use pure echo helpers and never open a desktop."""
import os
import signal
import sys
import time
from concurrent.futures import CancelledError
from threading import Event, Thread

import pytest

from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

HELPER = '''
import json, sys, time
for line in sys.stdin.buffer:
    request = json.loads(line)
    if request['operation'] == 'hang':
        time.sleep(30)
    if request['operation'] == 'event':
        print(json.dumps({'id': request['id'], 'event': {'kind': 'key_press', 'keycode': 65}}), flush=True)
        ack = json.loads(sys.stdin.buffer.readline())
        assert ack == {'ack': True}
    if request['operation'] == 'exit':
        sys.exit(2)
    print(json.dumps({'id': request['id'], 'result': request['payload']}), flush=True)
'''


def channel():
    return OwnedChannel([sys.executable, "-u", "-c", HELPER])


def test_round_trip_and_idempotent_owned_cleanup():
    worker = channel()
    try:
        assert worker.request("echo", {"value": 1}, timeout=5) == {"value": 1}
    finally:
        worker.close()
        worker.close()
    assert worker.retired


def test_hanging_helper_is_reaped_before_timeout_returns():
    worker = channel()
    started = time.monotonic()
    with pytest.raises(AgentTaskError, match="deadline"):
        worker.request("hang", {}, timeout=0.2)
    assert time.monotonic() - started < 5
    assert worker.retired


def test_cancelled_request_never_leaves_a_live_helper():
    worker = channel()
    cancelled = Event()
    cancelled.set()

    def check():
        if cancelled.is_set():
            raise CancelledError()

    with pytest.raises(CancelledError):
        worker.request("hang", {}, timeout=5, check=check)
    assert worker.retired


def test_input_notification_is_acknowledged_after_owner_check():
    worker = channel()
    events = []
    try:
        result = worker.request("event", {}, timeout=5, on_event=events.append)
        assert result == {}
        assert events == [{"kind": "key_press", "keycode": 65}]
    finally:
        worker.close()


def test_crashed_helper_is_reaped_and_never_reused():
    worker = channel()
    with pytest.raises(AgentTaskError):
        worker.request("exit", {}, timeout=5)
    assert worker.retired
    with pytest.raises(AgentTaskError):
        worker.request("echo", {}, timeout=1)


def test_close_from_another_thread_stops_a_waiting_request():
    worker = channel()
    outcome = {}

    def wait_for_reply():
        try:
            outcome["result"] = worker.request("hang", {}, timeout=20)
        except AgentTaskError as error:
            outcome["error"] = error

    waiter = Thread(target=wait_for_reply)
    waiter.start()
    time.sleep(0.3)
    started = time.monotonic()
    worker.close()
    closed_after = time.monotonic() - started
    waiter.join(timeout=5)
    assert not waiter.is_alive()
    assert closed_after < 5
    assert "result" not in outcome and "closed" in str(outcome["error"])
    assert worker.retired


def test_reply_already_queued_is_not_delivered_after_close():
    """The second check waits until the reply is queued; the third, which runs
    after the reply was dequeued and right before delivery, closes the channel."""
    worker = channel()
    closers = []
    state = {"calls": 0, "queued": False}

    def close_once_reply_is_dequeued():
        state["calls"] += 1
        if state["calls"] == 2:
            limit = time.monotonic() + 5
            while not worker._replies.qsize() and time.monotonic() < limit:
                time.sleep(0.01)
        if worker._replies.qsize():
            state["queued"] = True
        elif state["queued"] and not closers:
            closer = Thread(target=worker.close)
            closers.append(closer)
            closer.start()
            closer.join(timeout=5)
            assert not closer.is_alive()

    with pytest.raises(AgentTaskError, match="closed"):
        worker.request("echo", {"value": 1}, timeout=5, check=close_once_reply_is_dequeued)
    assert closers and worker.retired


def test_closed_channel_refuses_new_requests():
    worker = channel()
    worker.close()
    with pytest.raises(AgentTaskError, match="retired"):
        worker.request("echo", {}, timeout=1)


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups and SIGCHLD")


@posix_only
def test_ignored_sigchld_refuses_before_any_helper_starts():
    previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    try:
        with pytest.raises(AgentTaskError, match="SIGCHLD"):
            channel()
    finally:
        signal.signal(signal.SIGCHLD, previous)


@posix_only
def test_leader_reaped_elsewhere_is_never_signalled():
    worker = channel()
    pid = worker._process.pid
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)  # Another part of the process reaps it; the PID is free again.
    with pytest.raises(AgentTaskError, match="reaped elsewhere"):
        worker.close()
    assert not worker.retired
