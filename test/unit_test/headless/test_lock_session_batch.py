"""Headless tests for lock_session (injected driver / probe / clock)."""
import sys

import je_auto_control as ac
from je_auto_control.utils.lock_session import (
    classify_lock_transitions, lock_session, plan_lock_session,
    wait_for_lock, wait_for_unlock,
)


# --- lock action ----------------------------------------------------------

def test_lock_session_uses_driver():
    calls = []

    def fake_driver():
        calls.append(True)
        return True

    assert lock_session(driver=fake_driver) is True
    assert calls == [True]


def test_lock_session_driver_failure_reported():
    assert lock_session(driver=lambda: False) is False


def test_plan_lock_session_shape():
    plan = plan_lock_session()
    assert set(plan) == {"backend", "argv", "available"}
    assert plan["backend"] in ("LockWorkStation", "loginctl", "CGSession")
    assert isinstance(plan["available"], bool)


def test_plan_lock_session_available_per_os():
    plan = plan_lock_session()
    # Every supported platform path has a default backend.
    assert plan["available"] is True
    if plan["backend"] == "LockWorkStation":
        assert plan["argv"] is None
    else:
        assert isinstance(plan["argv"], list) and len(plan["argv"]) >= 1


# --- wait for unlock / lock -----------------------------------------------

def _probe_sequence(values):
    """Return a probe yielding successive booleans, repeating the last."""
    state = {"i": 0}

    def probe():
        i = min(state["i"], len(values) - 1)
        state["i"] += 1
        return values[i]

    return probe


def test_wait_for_unlock_returns_true_when_unlocked():
    # locked, locked, then unlocked -> returns True
    probe = _probe_sequence([True, True, False])
    clock = iter([0.0, 1.0, 2.0, 3.0, 4.0])
    ok = wait_for_unlock(probe=probe, timeout_s=10.0, interval_s=1.0,
                         clock=lambda: next(clock), sleep=lambda _s: None)
    assert ok is True


def test_wait_for_unlock_times_out_when_still_locked():
    probe = _probe_sequence([True])  # never unlocks
    times = iter([0.0, 0.0, 5.0, 10.0, 20.0])
    ok = wait_for_unlock(probe=probe, timeout_s=5.0, interval_s=1.0,
                         clock=lambda: next(times), sleep=lambda _s: None)
    assert ok is False


def test_wait_for_lock_returns_true_when_locked():
    probe = _probe_sequence([False, True])
    clock = iter([0.0, 1.0, 2.0, 3.0])
    ok = wait_for_lock(probe=probe, timeout_s=10.0, interval_s=1.0,
                       clock=lambda: next(clock), sleep=lambda _s: None)
    assert ok is True


# --- pure transition classifier -------------------------------------------

def test_classify_lock_transitions_events():
    events = classify_lock_transitions([False, False, True, True, False])
    assert events == [
        {"event": "lock", "locked": True},
        {"event": "unlock", "locked": False},
    ]


def test_classify_lock_transitions_empty_and_constant():
    assert classify_lock_transitions([]) == []
    assert classify_lock_transitions([True, True, True]) == []


# --- wiring ---------------------------------------------------------------

def test_executor_pure_classify_path():
    from je_auto_control.utils.executor.action_executor import (
        _classify_lock_transitions, _plan_lock_session,
    )
    out = _classify_lock_transitions([False, True])
    assert out == {"events": [{"event": "lock", "locked": True}]}
    # accepts a JSON-list string too (Script Builder text field)
    assert _classify_lock_transitions("[false, true]")["events"] == [
        {"event": "lock", "locked": True}]
    assert "backend" in _plan_lock_session()


def test_default_driver_absent_off_windows():
    from je_auto_control.utils.lock_session.lock_session import _default_driver
    if not sys.platform.startswith("win") and sys.platform != "darwin":
        # Linux default is loginctl (callable built), so a driver exists.
        assert callable(_default_driver())


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_lock_session", "AC_plan_lock_session", "AC_wait_for_unlock",
            "AC_classify_lock_transitions"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_lock_session", "ac_plan_lock_session", "ac_wait_for_unlock",
            "ac_classify_lock_transitions"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_lock_session", "AC_plan_lock_session", "AC_wait_for_unlock",
            "AC_classify_lock_transitions"} <= specs


def test_facade_exports():
    for name in ("lock_session", "plan_lock_session", "wait_for_unlock",
                 "wait_for_lock", "classify_lock_transitions"):
        assert hasattr(ac, name) and name in ac.__all__
