"""Headless tests for window client-area geometry. No Qt; reader is injected."""
import je_auto_control as ac
from je_auto_control.utils.window_geometry import (
    client_point, client_to_screen, frame_insets, get_client_rect,
)


def test_frame_insets():
    # window (100,100)-(300,250); client inset by an 8px border + 22px title bar
    insets = frame_insets((100, 100, 200, 150), (108, 122, 184, 120))
    assert insets == {"left": 8, "top": 22, "right": 8, "bottom": 8}


def test_client_to_screen():
    assert client_to_screen((108, 122, 184, 120), 10, 5) == (118, 127)


def test_get_client_rect_uses_reader():
    rect = get_client_rect("Editor", reader=lambda title: (108, 122, 184, 120))
    assert rect == (108, 122, 184, 120)


def test_get_client_rect_none_when_missing():
    assert get_client_rect("Nope", reader=lambda title: None) is None


def test_client_point_maps_into_window():
    point = client_point("Editor", 20, 30,
                         reader=lambda title: (108, 122, 184, 120))
    assert point == (128, 152)
    assert client_point("Gone", 1, 1, reader=lambda title: None) is None


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_get_client_rect", "AC_client_point"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_get_client_rect", "ac_client_point"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_get_client_rect", "AC_client_point"} <= specs


def test_facade_exports():
    for attr in ("frame_insets", "client_to_screen", "get_client_rect",
                 "client_point"):
        assert hasattr(ac, attr) and attr in ac.__all__
