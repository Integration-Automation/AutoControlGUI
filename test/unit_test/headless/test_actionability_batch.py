"""Headless tests for the pre-action actionability gate. No Qt; clock is injected."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.actionability import (
    GateConfig, act_when_ready, wait_actionable,
)


class _Clock:
    """A fake clock that only advances when the gate sleeps (deterministic)."""

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def _config():
    clock = _Clock()
    return GateConfig(timeout_s=5.0, stable_for_s=0.3, poll_interval_s=0.1,
                      clock=clock.now, sleep=clock.sleep)


def test_becomes_actionable_once_visible_and_stable():
    calls = {"n": 0}

    def bbox():
        calls["n"] += 1
        return (10, 10, 40, 20) if calls["n"] >= 2 else None

    report = wait_actionable(bbox, config=_config())
    assert report.actionable is True and report.reason == "actionable"
    assert report.point == [30, 20]


def test_never_visible_times_out():
    report = wait_actionable(lambda: None, config=_config())
    assert report.actionable is False and report.reason == "not visible"


def test_moving_target_is_not_stable():
    counter = {"n": 0}

    def moving():
        counter["n"] += 1
        return (counter["n"], 10, 40, 20)        # x shifts every poll

    report = wait_actionable(moving, config=_config())
    assert report.actionable is False and report.reason == "not stable"


def test_disabled_blocks():
    report = wait_actionable(lambda: (0, 0, 10, 10), enabled_probe=lambda: False,
                             config=_config())
    assert report.actionable is False and report.reason == "disabled"


def test_occluded_blocks():
    report = wait_actionable(lambda: (0, 0, 10, 10), hit_tester=lambda point: False,
                             config=_config())
    assert report.actionable is False and report.reason == "occluded"


def test_region_sampler_must_settle():
    samples = {"n": 0}

    def churning(_bbox):
        samples["n"] += 1
        return samples["n"]                      # pixel token keeps changing

    report = wait_actionable(lambda: (0, 0, 10, 10), region_sampler=churning,
                             config=_config())
    assert report.actionable is False and report.reason == "not stable"


def test_act_when_ready_calls_action_with_center():
    clicked = []
    result = act_when_ready(lambda point: clicked.append(point) or "ok",
                            lambda: (10, 10, 40, 20), config=_config())
    assert result == "ok" and clicked == [[30, 20]]


def test_act_when_ready_raises_on_timeout():
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    with pytest.raises(AutoControlActionException):
        act_when_ready(lambda point: "never", lambda: None, config=_config())


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_wait_actionable" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_wait_actionable" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_wait_actionable" in specs


def test_facade_exports():
    for attr in ("wait_actionable", "act_when_ready", "ActionabilityReport",
                 "GateConfig"):
        assert hasattr(ac, attr) and attr in ac.__all__
