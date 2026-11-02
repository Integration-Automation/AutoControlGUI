"""A release waits out a queued task's brief claim, but never an operation still dispatching.

Two tasks on one target: while the first finished, the second's ``acquire``
held the target lock for one claim. ``release`` gave up at once, the first
task's input cleanup was reported unconfirmed, and a finished task went to
review (``waiting_user``) -- seen under load on Windows CI.
"""
import threading

from je_auto_control.utils.agent_runtime import ownership
from je_auto_control.utils.agent_runtime.ownership import ControlBroker
from je_auto_control.utils.agent_runtime.store import AgentTaskStore


def _broker(tmp_path):
    return ControlBroker(AgentTaskStore(tmp_path / "tasks.sqlite3"))


def _hold(broker, target, seconds):
    """Hold the target lock from another thread, as a claim or a dispatch does."""
    held, done = threading.Event(), threading.Event()

    def worker():
        with broker._lock(target):  # the lock acquire() and dispatch() take
            held.set()
            done.wait(seconds)
    thread = threading.Thread(target=worker)
    thread.start()
    assert held.wait(5)
    return done, thread


def test_a_release_waits_out_a_brief_claim(tmp_path):
    broker = _broker(tmp_path)
    lease = broker.acquire("fixture", "first")
    cleaned = []
    done, thread = _hold(broker, "fixture", 0.2)
    try:
        assert broker.release(lease, lambda: cleaned.append(True)) is True
    finally:
        done.set()
        thread.join(5)
    assert cleaned == [True]
    assert broker.acquire("fixture", "second").owner == "second"


def test_a_release_does_not_take_a_target_still_dispatching(tmp_path, monkeypatch):
    monkeypatch.setattr(ownership, "_RELEASE_WAIT_SECONDS", 0.1)
    broker = _broker(tmp_path)
    lease = broker.acquire("fixture", "first")
    done, thread = _hold(broker, "fixture", 5)
    try:
        assert broker.release(lease, lambda: None) is False
    finally:
        done.set()
        thread.join(5)
    assert broker.release(lease, lambda: None) is True
