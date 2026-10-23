"""Owned subprocess protocol tests use pure echo helpers and never open a desktop."""
import sys
import time
from concurrent.futures import CancelledError
from threading import Event

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
