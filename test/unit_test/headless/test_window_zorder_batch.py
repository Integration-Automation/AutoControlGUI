"""Headless tests for window z-order control. No Qt; driver is injected."""
import je_auto_control as ac
from je_auto_control.utils.window_zorder import (
    available_actions, bring_to_front, plan_zorder, send_to_back, set_topmost,
)


def _recorder():
    calls = []

    def driver(title, action):
        calls.append((title, action))
        return True

    return driver, calls


def test_plan_zorder_maps_constants():
    assert plan_zorder("top")["insert_after"] == 0
    assert plan_zorder("bottom")["insert_after"] == 1
    assert plan_zorder("topmost")["insert_after"] == -1
    assert plan_zorder("notopmost")["insert_after"] == -2
    assert plan_zorder("top")["flags"] == ["SWP_NOMOVE", "SWP_NOSIZE"]


def test_plan_zorder_unknown_raises():
    try:
        plan_zorder("sideways")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_set_topmost_on_and_off():
    driver, calls = _recorder()
    assert set_topmost("Editor", True, driver=driver) is True
    assert set_topmost("Editor", False, driver=driver) is True
    assert calls == [("Editor", "topmost"), ("Editor", "notopmost")]


def test_bring_to_front_and_send_to_back():
    driver, calls = _recorder()
    bring_to_front("Editor", driver=driver)
    send_to_back("Editor", driver=driver)
    assert calls == [("Editor", "top"), ("Editor", "bottom")]


def test_available_actions():
    assert set(available_actions()) == {"top", "bottom", "topmost", "notopmost"}


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_set_topmost", "AC_bring_to_front", "AC_send_to_back"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_set_topmost", "ac_bring_to_front", "ac_send_to_back"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_set_topmost", "AC_bring_to_front", "AC_send_to_back"} <= specs


def test_facade_exports():
    for attr in ("plan_zorder", "set_topmost", "bring_to_front", "send_to_back"):
        assert hasattr(ac, attr) and attr in ac.__all__
