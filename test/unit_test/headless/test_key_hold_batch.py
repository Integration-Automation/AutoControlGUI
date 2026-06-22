"""Headless tests for key hold / auto-repeat. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.key_hold import hold_key, plan_key_hold


def test_hold_plan_press_wait_release():
    plan = plan_key_hold("key_d", 1.5)
    assert plan == [
        {"op": "press", "key": "key_d"},
        {"op": "wait", "seconds": 1.5},
        {"op": "release", "key": "key_d"},
    ]


def test_repeat_plan_emits_n_key_events():
    plan = plan_key_hold("a", 1.0, rate_hz=20)
    keys = [event for event in plan if event["op"] == "key"]
    waits = [event for event in plan if event["op"] == "wait"]
    assert len(keys) == 20
    assert len(waits) == 19                 # one fewer gap than events
    assert waits[0]["seconds"] == 0.05      # 1 / 20 Hz


def test_repeat_rounds_count_min_one():
    assert len([e for e in plan_key_hold("a", 0.01, rate_hz=10)
                if e["op"] == "key"]) == 1   # round(0.1) -> 0 -> clamped to 1


def test_hold_key_routes_waits_to_sleep():
    events, slept = [], []
    result = hold_key("a", 0.5, sink=events.append, sleep=slept.append)
    assert [e["op"] for e in events] == ["press", "release"]
    assert slept == [0.5]
    assert result["ops"] == 3


def test_validation():
    for bad in (("a", 0), ("a", -1)):
        try:
            plan_key_hold(*bad)
        except ValueError:
            pass
        else:                               # pragma: no cover
            raise AssertionError("expected ValueError")
    try:
        plan_key_hold("a", 1.0, rate_hz=0)
    except ValueError:
        pass
    else:                                   # pragma: no cover
        raise AssertionError("expected ValueError for rate_hz=0")


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_planning():
    events, slept = [], []
    from je_auto_control.utils.key_hold import hold_key as _hk
    _hk("space", 0.2, sink=events.append, sleep=slept.append)
    assert events[0]["op"] == "press" and events[-1]["op"] == "release"


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_hold_key" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_hold_key" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_hold_key" in specs


def test_facade_exports():
    for attr in ("plan_key_hold", "hold_key"):
        assert hasattr(ac, attr) and attr in ac.__all__
