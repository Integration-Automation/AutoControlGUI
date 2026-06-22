"""Headless tests for the eased / tweened drag. Pure math + injected sink
(no real mouse). Pure stdlib; no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.tween_drag import (
    easing_names, tween_drag, tween_points)


def test_tween_points_endpoints_and_count():
    points = tween_points((0, 0), (100, 50), steps=10, easing="linear")
    assert len(points) == 11
    assert points[0] == [0, 0] and points[-1] == [100, 50]
    assert points[5] == [50, 25]            # linear midpoint


def test_easing_changes_midpoint():
    linear = tween_points((0, 0), (100, 0), steps=10, easing="linear")
    eased = tween_points((0, 0), (100, 0), steps=10,
                         easing="ease_in_out_quad")
    # ease-in-out passes through the same midpoint but differs off-centre
    assert eased[5] == [50, 0]
    assert eased[2] != linear[2]
    assert "ease_in_out_quad" in easing_names()


def test_tween_drag_dispatches_press_moves_release():
    events = []
    out = tween_drag((0, 0), (10, 10), steps=4, sink=events.append)
    ops = [e["op"] for e in events]
    assert ops[0] == "press" and ops[-1] == "release"
    assert ops.count("move") == 5            # steps + 1 points
    assert out["points"] == 5
    assert events[-1]["x"] == 10 and events[-1]["y"] == 10


# --- wiring (registration only — executing moves the real mouse) ---------

def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_tween_drag" in known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    assert "ac_tween_drag" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_tween_drag" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("tween_points", "tween_drag", "easing_names"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
