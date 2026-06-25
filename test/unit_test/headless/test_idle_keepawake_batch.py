"""Headless tests for idle detection + keep-awake (injected probe / driver)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.idle_keepawake import (
    allow_sleep, idle_seconds, is_idle, keep_awake, keep_awake_on,
    plan_keep_awake,
)
from je_auto_control.utils.idle_keepawake.idle_keepawake import (
    _ES_CONTINUOUS, _ES_DISPLAY_REQUIRED, _ES_SYSTEM_REQUIRED,
)


def test_idle_seconds_uses_probe():
    assert idle_seconds(probe=lambda: 12.5) == pytest.approx(12.5)


def test_idle_seconds_clamps_negative():
    assert idle_seconds(probe=lambda: -3.0) == pytest.approx(0.0)


def test_is_idle_threshold():
    assert is_idle(5, probe=lambda: 9.0) is True
    assert is_idle(15, probe=lambda: 9.0) is False


def test_is_idle_rejects_negative_threshold():
    with pytest.raises(ValueError):
        is_idle(-1, probe=lambda: 0.0)


def test_plan_keep_awake_flags():
    plan = plan_keep_awake(display=True, system=True)
    assert plan["flags"] == (_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
                             | _ES_DISPLAY_REQUIRED)
    assert plan["display"] is True and plan["system"] is True
    assert plan["backend"] in ("SetThreadExecutionState", "caffeinate",
                               "systemd-inhibit")


def test_plan_keep_awake_system_only_omits_display_flag():
    plan = plan_keep_awake(display=False, system=True)
    assert plan["flags"] & _ES_DISPLAY_REQUIRED == 0
    assert plan["flags"] & _ES_SYSTEM_REQUIRED == _ES_SYSTEM_REQUIRED


def test_plan_keep_awake_rejects_all_false():
    with pytest.raises(ValueError):
        plan_keep_awake(display=False, system=False)


def test_keep_awake_context_acquires_and_releases():
    events = []

    def fake_driver(plan):
        events.append(("acquire", plan["flags"]))
        return lambda: events.append(("release", None))

    with keep_awake(driver=fake_driver) as plan:
        assert plan["backend"] is not None
        assert events == [("acquire", plan["flags"])]
    assert events[-1] == ("release", None)


def test_keep_awake_on_then_allow_sleep():
    released = []
    plan = keep_awake_on(driver=lambda p: lambda: released.append(True))
    assert plan["system"] is True
    assert allow_sleep() is True
    assert released == [True]


def test_allow_sleep_when_nothing_active():
    allow_sleep()  # drain any prior state
    assert allow_sleep() is False


def test_keep_awake_on_replaces_prior_request():
    released = []
    keep_awake_on(driver=lambda p: lambda: released.append("first"))
    keep_awake_on(driver=lambda p: lambda: released.append("second"))
    assert released == ["first"]  # prior request released on replace
    assert allow_sleep() is True
    assert released == ["first", "second"]


# --- wiring ---------------------------------------------------------------

def test_executor_pure_plan_path():
    from je_auto_control.utils.executor.action_executor import _plan_keep_awake
    plan = _plan_keep_awake(display=True, system=False)
    assert plan["flags"] & _ES_DISPLAY_REQUIRED == _ES_DISPLAY_REQUIRED


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_idle_seconds", "AC_is_idle", "AC_plan_keep_awake",
            "AC_keep_awake_on", "AC_allow_sleep"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_idle_seconds", "ac_is_idle", "ac_plan_keep_awake",
            "ac_keep_awake_on", "ac_allow_sleep"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_idle_seconds", "AC_is_idle", "AC_plan_keep_awake",
            "AC_keep_awake_on", "AC_allow_sleep"} <= specs


def test_facade_exports():
    for name in ("idle_seconds", "is_idle", "plan_keep_awake",
                 "keep_awake", "keep_awake_on", "allow_sleep"):
        assert hasattr(ac, name) and name in ac.__all__
