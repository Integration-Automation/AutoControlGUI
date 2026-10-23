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
