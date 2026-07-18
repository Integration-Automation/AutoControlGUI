"""Round-3 audit regressions: plugin isolation, dedup, time-travel, BDD.

Covers findings 7 (plugin_sdk), 10 (dedup_window), 13 (time-travel action
index), and 14 (behave step registration). Fully headless.
"""
import sys
import types

import pytest


# --- Finding 7: plugin discovery skips a broken plugin -------------------

class _FakeEntryPoint:
    def __init__(self, name, factory):
        self.name = name
        self._factory = factory

    def load(self):
        return self._factory


def test_discover_plugins_skips_broken_plugin():
    from je_auto_control.utils.plugin_sdk.plugin_sdk import discover_plugins

    def good_factory():
        return {"AC_good": lambda: "ok"}

    def key_error_factory():
        raise KeyError("boom")  # outside the old catch tuple

    class _SyntaxErrorEP:
        name = "syntax"

        def load(self):
            raise SyntaxError("broken plugin module")

    points = [
        _FakeEntryPoint("bad", key_error_factory),
        _SyntaxErrorEP(),
        _FakeEntryPoint("good", good_factory),
    ]
    commands = discover_plugins(entry_points=points)
    assert "AC_good" in commands
    assert "bad" not in commands


# --- Finding 10: dedup window coerces int ids consistently ---------------

def test_dedup_window_dedupes_integer_ids():
    from je_auto_control.utils.dedup_window.dedup_window import DedupWindow
    clock = [1000.0]
    window = DedupWindow(60.0, clock=lambda: clock[0])
    window.mark(123)
    assert window.seen(123) is True
    assert window.check_and_mark(123) is False


def test_dedup_window_check_and_mark_int_first_seen():
    from je_auto_control.utils.dedup_window.dedup_window import DedupWindow
    clock = [1000.0]
    window = DedupWindow(60.0, clock=lambda: clock[0])
    assert window.check_and_mark(7) is True
    assert window.seen(7) is True
    assert window.check_and_mark(7) is False


# --- Finding 13: actions-only recording still yields an action index -----

def test_actions_only_recording_yields_action_index(tmp_path):
    from je_auto_control.utils.time_travel.controller import (
        TraceReplayController,
    )
    from je_auto_control.utils.time_travel.player import (
        ActionEvent, TimelinePlayer, save_action_log,
    )
    events = [
        ActionEvent(timestamp=1000.0, action_name="mouse_click", args={"x": 1}),
        ActionEvent(timestamp=1001.5, action_name="type_keyboard",
                    args={"text": "a"}),
    ]
    save_action_log(events, tmp_path / "actions.jsonl")

    player = TimelinePlayer(tmp_path)  # no manifest.json → total_steps == 0
    assert player.frame_count == 0
    assert player.action_count == 2

    controller = TraceReplayController(player)
    index = controller.action_index()
    assert len(index) == 2


# --- Finding 14: behave steps accept a leading context param -------------

def test_behave_wrap_forwards_params_and_accepts_context():
    from je_auto_control.utils.pytest_plugin.bdd_steps import _behave_wrap
    seen = []
    wrapped = _behave_wrap(lambda text: seen.append(text) or "ok")
    result = wrapped(object(), text="hello")
    assert seen == ["hello"]
    assert result == "ok"


def test_register_behave_steps_wrappers_accept_context(monkeypatch):
    from je_auto_control.utils.pytest_plugin.bdd_steps import (
        register_behave_steps,
    )
    registered = {}

    def factory(pattern):
        def decorator(func):
            registered[pattern] = func
            return func
        return decorator

    fake_behave = types.ModuleType("behave")
    fake_behave.given = factory
    fake_behave.when = factory
    fake_behave.then = factory
    monkeypatch.setitem(sys.modules, "behave", fake_behave)

    register_behave_steps()
    ready_step = registered["AutoControl is ready"]
    # behave calls func(context); the raw 0-arg step would raise TypeError.
    ready_step(object())


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
