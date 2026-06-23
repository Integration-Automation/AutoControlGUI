"""Headless tests for the pre-action grounding guard. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.action_grounding import (
    in_bounds, snap_to_element, validate_action,
)

_ELEMENTS = [{"x": 100, "y": 100, "width": 40, "height": 20},
             {"x": 300, "y": 200, "width": 60, "height": 30}]


def test_in_bounds():
    assert in_bounds(50, 50, (1920, 1080)) is True
    assert in_bounds(9999, 5, (1920, 1080)) is False
    assert in_bounds(-1, 5, (1920, 1080)) is False


def test_snap_inside_and_near_and_far():
    assert snap_to_element(110, 108, _ELEMENTS) == [120, 110]      # inside el1
    assert snap_to_element(122, 112, _ELEMENTS, max_dist=8) == [120, 110]
    assert snap_to_element(500, 500, _ELEMENTS, max_dist=8) is None


def test_validate_rejects_out_of_bounds():
    result = validate_action({"type": "click", "x": 9999, "y": 5},
                             screen_size=(1920, 1080))
    assert result["ok"] is False and result["reason"] == "out of bounds"


def test_validate_snaps_near_miss():
    result = validate_action({"type": "click", "x": 118, "y": 109},
                             screen_size=(1920, 1080), targets=_ELEMENTS)
    assert result["ok"] is True and result["snapped"] == [120, 110]


def test_validate_in_bounds_no_snap():
    result = validate_action({"type": "click", "x": 500, "y": 500},
                             screen_size=(1920, 1080), targets=_ELEMENTS)
    assert result["ok"] is True and result["reason"] == "in bounds"
    assert result["snapped"] is None


def test_validate_no_coordinate_passes():
    result = validate_action({"type": "type", "text": "hi"},
                             screen_size=(1920, 1080))
    assert result["ok"] is True and result["reason"] == "no coordinate"


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_validate_action" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_validate_action" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_validate_action" in specs


def test_facade_exports():
    for attr in ("in_bounds", "snap_to_element", "validate_action"):
        assert hasattr(ac, attr) and attr in ac.__all__
