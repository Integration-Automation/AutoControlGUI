"""Headless tests for app_idle (settle gate over an injected busy probe)."""
import je_auto_control as ac
from je_auto_control.utils.app_idle import idle_point, wait_until_app_idle


# --- pure idle_point ------------------------------------------------------

def test_idle_point_after_busy_run():
    # busy, busy, idle, idle, idle -> settles at index 4 (3 quiet in a row)
    samples = [True, True, False, False, False]
    assert idle_point(samples, quiet_samples=3) == 4


def test_idle_point_resets_on_spike():
    # idle, idle, BUSY, idle, idle, idle -> the spike resets the quiet run
    samples = [False, False, True, False, False, False]
    assert idle_point(samples, quiet_samples=3) == 5


def test_idle_point_never_settles():
    assert idle_point([True, True, True], quiet_samples=2) is None


def test_idle_point_immediate_when_quiet_one():
    assert idle_point([False], quiet_samples=1) == 0


# --- wait_until_app_idle --------------------------------------------------

def _probe_sequence(values):
    state = {"i": 0}

    def probe():
        i = min(state["i"], len(values) - 1)
        state["i"] += 1
        return values[i]

    return probe


def test_wait_until_app_idle_settles():
    # busy then idle x3 -> idle=True
    probe = _probe_sequence([True, False, False, False])
    clock = iter([0.0, 0.0, 1.0, 2.0, 3.0, 4.0])
    result = wait_until_app_idle(busy_probe=probe, quiet_samples=3,
                                 timeout_s=100.0, interval_s=1.0,
                                 clock=lambda: next(clock),
                                 sleep=lambda _s: None)
    assert result["idle"] is True
    assert result["quiet_run"] >= 3


def test_wait_until_app_idle_times_out_when_busy():
    probe = _probe_sequence([True])  # always busy
    ticks = iter([0.0, 1.0, 2.0, 6.0, 7.0])
    result = wait_until_app_idle(busy_probe=probe, quiet_samples=3,
                                 timeout_s=5.0, interval_s=1.0,
                                 clock=lambda: next(ticks),
                                 sleep=lambda _s: None)
    assert result["idle"] is False


# --- wiring ---------------------------------------------------------------

def test_executor_pure_idle_point():
    from je_auto_control.utils.executor.action_executor import _idle_point
    out = _idle_point([True, False, False, False], 3)
    assert out["index"] == 3
    # accepts a JSON-list string (Script Builder text field)
    assert _idle_point("[false, false]", 2)["index"] == 1


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_wait_until_app_idle", "AC_idle_point"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_wait_until_app_idle", "ac_idle_point"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_wait_until_app_idle", "AC_idle_point"} <= specs


def test_facade_exports():
    for name in ("wait_until_app_idle", "idle_point"):
        assert hasattr(ac, name) and name in ac.__all__
