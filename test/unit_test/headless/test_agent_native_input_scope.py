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
