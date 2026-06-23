"""Headless tests for multi-window arrangers. No Qt; mover is injected."""
import je_auto_control as ac
from je_auto_control.utils.window_capture import arrange_cascade, arrange_grid


def _recorder():
    """Return (mover, calls) where mover records every move and reports success."""
    calls = []

    def mover(title, x, y, width, height):
        calls.append((title, x, y, width, height))
        return True

    return mover, calls


def _screen():
    return lambda: (1920, 1080)


def test_arrange_grid_tiles_four_windows_2x2():
    mover, calls = _recorder()
    moved = arrange_grid(["a", "b", "c", "d"], mover=mover, screen_size=_screen())
    assert moved == 4
    assert calls == [
        ("a", 0, 0, 960, 540), ("b", 960, 0, 960, 540),
        ("c", 0, 540, 960, 540), ("d", 960, 540, 960, 540)]


def test_arrange_grid_auto_shape_three_windows():
    mover, calls = _recorder()
    # 3 windows -> near-square 2x2 grid; the first three cells are used.
    moved = arrange_grid(["a", "b", "c"], mover=mover, screen_size=_screen())
    assert moved == 3
    assert [c[0] for c in calls] == ["a", "b", "c"]


def test_arrange_grid_explicit_rows_cols_and_gap():
    mover, calls = _recorder()
    arrange_grid(["a", "b", "c"], rows=1, cols=3, gap=10, mover=mover,
                 screen_size=_screen())
    assert calls[0] == ("a", 10, 10, 620, 1060)        # 640-wide cell, gap 10
    assert len(calls) == 3


def test_arrange_grid_empty_is_noop():
    mover, calls = _recorder()
    assert arrange_grid([], mover=mover, screen_size=_screen()) == 0
    assert calls == []


def test_arrange_cascade_staggers_windows():
    mover, calls = _recorder()
    moved = arrange_cascade(["a", "b", "c"], offset=40, mover=mover,
                            screen_size=_screen())
    assert moved == 3
    assert calls[0][1:3] == (0, 0)
    assert calls[1][1:3] == (40, 40)
    assert calls[2][1:3] == (80, 80)
    assert all(c[3] == 1152 and c[4] == 648 for c in calls)   # 60% of 1920x1080


def test_arrange_counts_only_successful_moves():
    calls = []

    def flaky(title, x, y, width, height):
        calls.append(title)
        return title != "b"           # "b" fails to move

    moved = arrange_grid(["a", "b", "c", "d"], mover=flaky, screen_size=_screen())
    assert moved == 3 and len(calls) == 4


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_arrange_grid", "AC_arrange_cascade"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_arrange_grid", "ac_arrange_cascade"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_arrange_grid", "AC_arrange_cascade"} <= specs


def test_facade_exports():
    for attr in ("arrange_grid", "arrange_cascade"):
        assert hasattr(ac, attr) and attr in ac.__all__
