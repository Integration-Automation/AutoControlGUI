"""Headless tests for relative mouse movement. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlMouseException
from je_auto_control.utils.mouse_relative import (
    move_mouse_relative, relative_target,
)


def test_relative_target_arithmetic():
    assert relative_target((100, 100), -40, 12) == (60, 112)
    assert relative_target((0, 0), 0, 0) == (0, 0)


def test_move_uses_current_position_plus_delta():
    moves = []
    result = move_mouse_relative(
        10, -5, get_position=lambda: (200, 200),
        set_position=lambda x, y: moves.append((x, y)))
    assert moves == [(210, 195)]
    assert result == {"from": [200, 200], "to": [210, 195], "delta": [10, -5]}


def test_raises_when_position_unreadable():
    try:
        move_mouse_relative(1, 1, get_position=lambda: None,
                            set_position=lambda x, y: None)
    except AutoControlMouseException:
        pass
    else:                                  # pragma: no cover
        raise AssertionError("expected AutoControlMouseException")


# --- wiring ---------------------------------------------------------------

def test_executor_adapter_planning():
    # the default backend get/set is device-bound; exercise the pure arithmetic
    # the adapter relies on instead.
    assert relative_target((5, 5), 3, 4) == (8, 9)


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_move_mouse_relative" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_move_mouse_relative" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_move_mouse_relative" in specs


def test_facade_exports():
    for attr in ("move_mouse_relative", "relative_target"):
        assert hasattr(ac, attr) and attr in ac.__all__
