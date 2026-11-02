"""Presence gates use synthetic metadata and never install native hooks in tests."""
import pytest

from je_auto_control.utils.agent_runtime.activity import ActivityGate, physical_event
from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError


class Listener:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def alive(self):
        return self.running


def test_shared_desktop_waits_for_unlocked_idle_session():
    listener, takeover = Listener(), []
    idle, unlocked = [59], [True]
    gate = ActivityGate(listener, lambda: idle[0], lambda: unlocked[0], lambda: takeover.append(True))
    try:
        with pytest.raises(AgentControlBusy):
            gate.ready()
        idle[0], unlocked[0] = 61, False
        with pytest.raises(AgentControlBusy):
            gate.ready()
        unlocked[0] = True
        gate.ready()
        gate.notify()
        gate.notify()
        assert takeover == [True]
        with pytest.raises(AgentTaskError, match="human input"):
            gate.check()
    finally:
        gate.close()
    assert not listener.running


def test_injected_input_is_distinguished_using_native_metadata():
    assert physical_event("keyboard", 0)
    assert physical_event("mouse", 0)
    assert not physical_event("keyboard", 0x10)
    assert not physical_event("mouse", 1)


def test_listener_loss_refuses_further_input():
    listener = Listener()
    gate = ActivityGate(listener, lambda: 61, lambda: True, lambda: None)
    gate.ready()
    listener.running = False
    with pytest.raises(AgentTaskError, match="monitoring"):
        gate.check()
