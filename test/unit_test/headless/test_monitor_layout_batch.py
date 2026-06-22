"""Headless tests for multi-monitor geometry. No Qt; provider is injected."""
import je_auto_control as ac
from je_auto_control.utils.monitor_layout import (
    Monitor, enumerate_monitors, monitor_at_point, monitor_for_window,
    primary_monitor, remap_point, to_local, to_virtual, virtual_bounds,
)


def _two_monitors():
    # primary 1920x1080 at origin; secondary 1280x1024 to the LEFT (negative x)
    return [
        Monitor(0, 0, 0, 1920, 1080, scale=1.0, primary=True),
        Monitor(1, -1280, 0, 1280, 1024, scale=1.25),
    ]


def test_virtual_bounds_spans_negative_origin():
    assert virtual_bounds(_two_monitors()) == (-1280, 0, 3200, 1080)


def test_virtual_bounds_empty_raises():
    try:
        virtual_bounds([])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_primary_monitor():
    assert primary_monitor(_two_monitors()).index == 0


def test_monitor_at_point():
    mons = _two_monitors()
    assert monitor_at_point(mons, 100, 100).index == 0
    assert monitor_at_point(mons, -200, 100).index == 1     # on the left monitor
    assert monitor_at_point(mons, 5000, 5000) is None


def test_monitor_for_window_max_overlap():
    mons = _two_monitors()
    # window mostly on the secondary (left) monitor
    assert monitor_for_window((-1000, 50, 400, 300), mons).index == 1
    assert monitor_for_window((10, 10, 400, 300), mons).index == 0
    assert monitor_for_window((9000, 9000, 10, 10), mons) is None


def test_to_local_and_back():
    mons = _two_monitors()
    assert to_local(mons, -200, 100) == (1, 1080, 100)      # local within monitor 1
    assert to_virtual(mons[1], 1080, 100) == (-200, 100)
    assert to_local(mons, 9000, 9000) is None


def test_remap_point_preserves_fraction():
    src, dst = _two_monitors()                              # 1920x1080 -> 1280x1024
    # centre of src maps to centre of dst
    assert remap_point(src, dst, 960, 540) == (640, 512)
    assert remap_point(src, dst, 0, 0) == (0, 0)


def test_enumerate_monitors_with_injected_provider():
    rows = [{"x": 0, "y": 0, "width": 1920, "height": 1080, "primary": True},
            {"x": 1920, "y": 0, "width": 1280, "height": 1024, "scale": 1.5}]
    mons = enumerate_monitors(provider=lambda: rows)
    assert [m.index for m in mons] == [0, 1]
    assert mons[0].primary is True and mons[1].scale == 1.5
    assert mons[1].x == 1920


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_enumerate_monitors", "AC_monitor_at_point"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_enumerate_monitors", "ac_monitor_at_point"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_enumerate_monitors", "AC_monitor_at_point"} <= specs


def test_facade_exports():
    for attr in ("Monitor", "enumerate_monitors", "monitor_at_point",
                 "virtual_bounds", "remap_point", "to_local", "to_virtual"):
        assert hasattr(ac, attr) and attr in ac.__all__
