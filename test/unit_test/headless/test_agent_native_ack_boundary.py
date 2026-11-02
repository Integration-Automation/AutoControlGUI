"""Exercise actual worker/observer ACK boundaries without hooks, windows or native input."""
import io
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.activity import ActivityGate
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper import auto_control_keyboard as keyboard
from je_auto_control.wrapper._input_observer import input_observer


class Boundary:
    """Replace only the OS backend and the owner's ACK stream, keeping real wrapper dispatch."""

    def __init__(self, monkeypatch):
        self.events = []
        self.activity_valid = self.target_valid = True
        self.reply = b'{"ack": true}\n'
        self.on_ack = self.on_prepare = lambda: None
        self.sink = io.BytesIO()
        self.worker = NativeWorker(self, self.sink, target=self)
        self.worker._activity = SimpleNamespace(check=self.check_activity)
        monkeypatch.setattr(keyboard, "keyboard", SimpleNamespace(
            press_key=lambda *a, **k: self.events.append("pressed"),
            release_key=lambda *a, **k: self.events.append("released"),
            release_unicode=lambda *a: self.events.append("released unicode")))

    def check_activity(self):
        self.events.append("activity")
        if not self.activity_valid:
            raise AgentTaskError("activity changed during ACK")

    def validate_input(self, _event):
        self.events.append("target")
        if not self.target_valid:
            raise AgentTaskError("target changed during ACK")

    def prepare_input(self, _event):
        self.events.append("prepared")
        self.on_prepare()

    def readline(self, _limit):
        self.events.append("ACK")
        self.on_ack()
        return self.reply

    def cleanup(self):
        self.events.append("cleaned")

    def press(self):
        with input_observer(self.worker._input):
            keyboard.press_keyboard_key(65, skip_record=True)


@pytest.mark.parametrize("invalid,monitor", [("activity", True), ("target", True), ("target", False)])
def test_ack_time_invalidation_prevents_actual_wrapper_backend(monkeypatch, invalid, monitor):
    boundary = Boundary(monkeypatch)
    if not monitor:
        boundary.worker._activity = None
    boundary.on_ack = lambda: setattr(boundary, invalid + "_valid", False)
    with pytest.raises(AutoControlException, match=invalid + " changed"):
        boundary.press()
    assert "pressed" not in boundary.events
    assert boundary.events.count("ACK") == 1


def test_healthy_input_rechecks_after_ack_before_actual_backend(monkeypatch):
    boundary = Boundary(monkeypatch)
    boundary.press()
    assert boundary.events == ["activity", "target", "ACK", "activity", "target", "pressed"]


def test_actual_activity_gate_takeover_during_ack_refuses_backend(monkeypatch):
    boundary, notices = Boundary(monkeypatch), []
    listener = SimpleNamespace(start=lambda: None, alive=lambda: True, stop=lambda: None)
    gate = ActivityGate(listener, lambda: 60, lambda: True, lambda: notices.append("takeover"))
    boundary.worker._activity = gate
    gate.ready()
    boundary.on_ack = gate.notify
    try:
        with pytest.raises(AutoControlException, match="human input"):
            boundary.press()
        assert notices == ["takeover"]
        assert "pressed" not in boundary.events
        with pytest.raises(AgentTaskError, match="explicit resume"):
            gate.check()
    finally:
        gate.close()


@pytest.mark.parametrize("reply", [b'', b'{"ack": false}\n', b'{"ack": true, "other": 1}\n',
                                 b'broken\n', b'{"ack": 1}\n', b'{"ack": 1.0}\n'])
def test_bad_ack_never_reaches_post_ack_permission_or_backend(monkeypatch, reply):
    boundary = Boundary(monkeypatch)
    boundary.reply = reply
    with pytest.raises(AutoControlException):
        boundary.press()
    assert boundary.events == ["activity", "target", "ACK"]


def test_pre_ack_refusal_does_not_send_or_wait_for_an_event(monkeypatch):
    boundary = Boundary(monkeypatch)
    boundary.target_valid = False
    with pytest.raises(AutoControlException, match="target changed"):
        boundary.press()
    assert boundary.sink.getvalue() == b''
    assert boundary.events == ["activity", "target"]


def test_mouse_preparation_takeover_refuses_outer_press_before_ack(monkeypatch):
    boundary = Boundary(monkeypatch)
    boundary.on_prepare = lambda: setattr(boundary, "activity_valid", False)
    with pytest.raises(AgentTaskError, match="activity changed"):
        boundary.worker._input({"kind": "mouse_press", "move_before_press": True})
    assert boundary.sink.getvalue() == b''
    assert boundary.events == ["activity", "target", "prepared", "activity"]


@pytest.mark.parametrize("unicode", [False, True])
def test_owned_release_cleanup_survives_takeover_and_target_loss(monkeypatch, unicode):
    boundary = Boundary(monkeypatch)
    boundary.activity_valid = boundary.target_valid = False
    key = {"keycode": 0x4E2D if unicode else 65, "is_shift": False}
    if unicode:
        key["unicode"] = True
    assert boundary.worker._release_owned({"keys": [key], "buttons": []}) == {"cleaned": True}
    assert boundary.events == ["ACK", "released unicode" if unicode else "released", "ACK", "cleaned"]
    assert not boundary.worker._cleanup


def test_owned_mouse_release_cleanup_never_moves_or_presses(monkeypatch):
    from je_auto_control.wrapper import auto_control_mouse as mouse
    boundary = Boundary(monkeypatch)
    boundary.activity_valid = boundary.target_valid = False
    monkeypatch.setattr(mouse, "mouse_keys_table", {"mouse_left": 1})
    monkeypatch.setattr(mouse, "mouse", SimpleNamespace(
        release_mouse=lambda *a: boundary.events.append("released mouse")))
    payload = {"keys": [], "buttons": [{"keycode": "mouse_left", "x": 0, "y": 0}]}
    assert boundary.worker._release_owned(payload) == {"cleaned": True}
    assert boundary.events == ["ACK", "released mouse", "ACK", "cleaned"]
    assert not boundary.worker._cleanup


def test_rejected_cleanup_ack_retains_failure_and_resets_cleanup_mode(monkeypatch):
    boundary = Boundary(monkeypatch)
    boundary.reply = b'{"ack": false}\n'
    payload = {"keys": [{"keycode": 65, "is_shift": False}], "buttons": []}
    with pytest.raises(AgentTaskError, match="cleanup is incomplete"):
        boundary.worker._release_owned(payload)
    assert not boundary.worker._cleanup
    assert boundary.events == ["ACK"]


@pytest.mark.parametrize("kind", ["key_press", "mouse_press", "pointer", "text", "scroll", "unknown"])
def test_cleanup_observer_cannot_authorize_fresh_input(monkeypatch, kind):
    boundary = Boundary(monkeypatch)
    boundary.worker._cleanup = True
    with pytest.raises(AgentTaskError, match="release"):
        boundary.worker._input({"kind": kind})
    assert boundary.sink.getvalue() == b''
    assert boundary.events == []
