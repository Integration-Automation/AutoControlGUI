"""Native input observation is opt-in and tested against fake platform drivers."""
from unittest.mock import patch

import pytest

from je_auto_control.wrapper._input_observer import input_observer


def test_key_events_are_announced_before_press_and_after_release():
    from je_auto_control.wrapper import auto_control_keyboard as keyboard
    events = []
    with patch.object(keyboard.keyboard, "press_key", side_effect=lambda *a, **k: events.append("pressed")):
        with patch.object(keyboard.keyboard, "release_key", side_effect=lambda *a, **k: events.append("released")):
            with input_observer(lambda event: events.append(event["kind"])):
                keyboard.press_keyboard_key("a")
                keyboard.release_keyboard_key("a")
    assert events == ["key_press", "pressed", "key_release", "released", "key_released"]


def test_rejected_input_never_calls_native_driver():
    from je_auto_control.wrapper import auto_control_keyboard as keyboard
    from je_auto_control.utils.exception.exceptions import AutoControlException
    calls = []

    def refuse(_event):
        raise ValueError("owner refused")

    with patch.object(keyboard.keyboard, "press_key", side_effect=lambda *a, **k: calls.append(True)):
        with input_observer(refuse), pytest.raises(AutoControlException):
            keyboard.press_keyboard_key("a")
    assert calls == []


def test_unicode_press_and_release_are_individually_owned(monkeypatch):
    from types import SimpleNamespace
    from je_auto_control.wrapper import auto_control_keyboard as keyboard
    from je_auto_control.utils.agent_runtime.input_ledger import InputLedger
    calls, ledger = [], InputLedger()
    driver = SimpleNamespace(type_unicode_unit=lambda _unit: pytest.fail("opaque Unicode dispatch"),
                             press_unicode=lambda unit: calls.append(("down", unit)),
                             release_unicode=lambda unit: calls.append(("up", unit)))
    monkeypatch.setattr(keyboard, "keyboard", driver)
    with input_observer(ledger.consume):
        assert keyboard._write_char_via_unicode("中")
    assert calls == [("down", ord("中")), ("up", ord("中"))]
    assert ledger.empty


def test_modifier_release_cannot_claim_an_unowned_modifier():
    from je_auto_control.utils.agent_runtime.input_ledger import InputLedger
    from je_auto_control.utils.agent_runtime import AgentTaskError
    ledger = InputLedger()
    ledger.consume({"kind": "key_press", "keycode": 65, "is_shift": False})
    with pytest.raises(AgentTaskError, match="modifier"):
        ledger.consume({"kind": "key_release", "keycode": 65, "is_shift": True})
    assert not ledger.empty


def test_managed_mouse_press_announces_positioning_before_any_button_input(monkeypatch):
    from je_auto_control.wrapper import auto_control_mouse as mouse
    events = []
    monkeypatch.setattr(mouse.mouse, "press_mouse", lambda *args: None)
    with input_observer(events.append):
        mouse.press_mouse("left", 30, 40)
    assert events[0]["move_before_press"] is True
    assert isinstance(events[0]["keycode"], (str, int))
    assert (events[0]["x"], events[0]["y"]) == (30, 40)


def test_desktop_prepares_and_confirms_pointer_before_acknowledging_button(monkeypatch):
    import io
    from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
    from je_auto_control.utils.agent_runtime.targets import DesktopTarget
    from je_auto_control.wrapper import auto_control_mouse as mouse
    events, position = [], [1, 2]

    class Sink(io.BytesIO):
        def write(self, value):
            events.append("acknowledge press")
            return super().write(value)

    def move(x, y):
        events.append("position")
        position[:] = [x, y]

    target = DesktopTarget()
    monkeypatch.setattr(target, "validate_input", lambda _event: events.append("validate"))
    monkeypatch.setattr(mouse, "set_mouse_position", move)
    monkeypatch.setattr(mouse, "get_mouse_position", lambda: tuple(position))
    worker = NativeWorker(io.BytesIO(b'{"ack": true}\n'), Sink(), target=target)
    worker._input({"kind": "mouse_press", "keycode": "left", "x": 30, "y": 40, "move_before_press": True})
    assert events == ["validate", "position", "validate", "acknowledge press"]


def test_failed_pointer_positioning_never_acknowledges_a_press(monkeypatch):
    import io
    from je_auto_control.utils.agent_runtime.native_worker import NativeWorker
    from je_auto_control.utils.agent_runtime.targets import DesktopTarget
    from je_auto_control.utils.agent_runtime import AgentTaskError
    from je_auto_control.wrapper import auto_control_mouse as mouse
    target, sink = DesktopTarget(), io.BytesIO()
    monkeypatch.setattr(target, "validate_input", lambda _event: None)
    monkeypatch.setattr(mouse, "set_mouse_position", lambda *_args: None)
    monkeypatch.setattr(mouse, "get_mouse_position", lambda: (1, 2))
    worker = NativeWorker(io.BytesIO(b'{"ack": true}\n'), sink, target=target)
    with pytest.raises(AgentTaskError, match="position"):
        worker._input({"kind": "mouse_press", "keycode": "left", "x": 30, "y": 40, "move_before_press": True})
    assert sink.getvalue() == b""
