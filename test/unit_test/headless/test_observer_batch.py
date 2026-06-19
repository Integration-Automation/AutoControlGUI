"""Headless tests for the reactive screen observer. Pure stdlib; detection
is injected via fake predicates so no real screen is required."""
import je_auto_control as ac
from je_auto_control.utils.observer import (
    EVENT_APPEAR, EVENT_CHANGE, EVENT_VANISH, ScreenObserver)


class _Source:
    """A mutable predicate source for driving transitions in tests."""

    def __init__(self, value=None):
        self.value = value

    def __call__(self):
        return self.value


def test_appear_vanish_change_transitions():
    obs = ScreenObserver()
    src = _Source(None)
    seen = []
    obs.add("w", src, lambda event, value: seen.append(event))

    assert obs.poll_once() == []          # absent -> no event
    src.value = (10, 20)
    assert obs.poll_once()[0]["event"] == EVENT_APPEAR
    assert obs.poll_once() == []          # unchanged -> no event
    src.value = (30, 40)
    assert obs.poll_once()[0]["event"] == EVENT_CHANGE
    src.value = None
    assert obs.poll_once()[0]["event"] == EVENT_VANISH
    assert seen == [EVENT_APPEAR, EVENT_CHANGE, EVENT_VANISH]


def test_event_filter_only_fires_selected():
    obs = ScreenObserver()
    src = _Source(None)
    fired = []
    obs.add("only-appear", src, lambda e, v: fired.append(e),
            events=(EVENT_APPEAR,))
    src.value = "here"
    obs.poll_once()
    src.value = None
    obs.poll_once()                       # vanish ignored (not subscribed)
    assert fired == [EVENT_APPEAR]


def test_predicate_error_does_not_break_loop():
    obs = ScreenObserver()

    def boom():
        raise RuntimeError("predicate failed")

    obs.add("bad", boom, lambda e, v: None)
    assert obs.poll_once() == []          # error swallowed, no crash


def test_remove_and_names_and_fired_log():
    obs = ScreenObserver()
    obs.add("a", _Source("x"), lambda e, v: None)
    obs.add("b", _Source(None), lambda e, v: None)
    assert set(obs.names()) == {"a", "b"}
    obs.poll_once()
    assert obs.fired and obs.fired[-1]["rule"] == "a"
    assert obs.remove("a") is True
    assert obs.remove("a") is False
    assert obs.names() == ["b"]


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    from je_auto_control.utils.observer import default_observer
    default_observer.clear()
    ac.execute_action([["AC_observe_add", {
        "name": "img", "kind": "image", "event": "appear",
        "image": "missing.png", "actions": []}]])
    listing = ac.execute_action([["AC_observe_list", {}]])
    assert any("img" in str(v) for v in listing.values())
    # poll is safe even though the image backend isn't available headless
    polled = ac.execute_action([["AC_observe_poll", {}]])
    assert any("fired" in str(v) for v in polled.values())
    ac.execute_action([["AC_observe_remove", {"name": "img"}]])
    known = ac.executor.known_commands()
    assert {"AC_observe_add", "AC_observe_remove", "AC_observe_list",
            "AC_observe_poll", "AC_observe_start", "AC_observe_stop"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_observe_add", "ac_observe_remove", "ac_observe_list",
            "ac_observe_poll", "ac_observe_start", "ac_observe_stop"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_observe_add", "AC_observe_remove", "AC_observe_list",
            "AC_observe_poll", "AC_observe_start", "AC_observe_stop"} <= cmds


def test_facade_exports():
    for attr in ("ScreenObserver", "WatchRule", "default_observer",
                 "image_predicate", "pixel_predicate", "text_predicate"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
