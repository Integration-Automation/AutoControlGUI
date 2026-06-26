"""Headless tests for act_in_view (injected locator / scroller / action / gate)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.act_in_view import ScrollPlan, act_in_view
from je_auto_control.utils.actionability import GateConfig
from je_auto_control.utils.exception.exceptions import AutoControlActionException


def _locator_found_after(scrolls_needed, coords=(100, 200)):
    """A locator that returns None until ``scrolls_needed`` scrolls, then coords."""
    state = {"calls": 0}

    def locator(_target):
        result = coords if state["calls"] >= scrolls_needed else None
        state["calls"] += 1
        return result

    return locator


# --- scroll then act ------------------------------------------------------

def test_act_in_view_scrolls_then_acts():
    scrolled = []
    clicked = []
    plan = ScrollPlan(locator=_locator_found_after(2, (100, 200)),
                      scroller=lambda direction, amount: scrolled.append(
                          (direction, amount)),
                      max_scrolls=5)
    out = act_in_view("target.png", clicked.append, scroll=plan)
    assert out["acted"] is True
    assert out["coords"] == [100, 200]
    assert out["scrolls"] == 2
    assert clicked == [[100, 200]]   # acted at the located point
    assert len(scrolled) == 2         # scrolled twice before finding


def test_act_in_view_acts_immediately_when_already_visible():
    clicked = []
    plan = ScrollPlan(locator=lambda _t: (50, 60),
                      scroller=lambda d, a: None)
    out = act_in_view("here", clicked.append, scroll=plan)
    assert out["scrolls"] == 0
    assert clicked == [[50, 60]]


def test_act_in_view_raises_when_never_found():
    plan = ScrollPlan(locator=lambda _t: None,
                      scroller=lambda d, a: None, max_scrolls=3)
    with pytest.raises(AutoControlActionException):
        act_in_view("missing", lambda point: None, scroll=plan)


# --- actionability gate is honoured ---------------------------------------

def test_act_in_view_waits_for_enabled():
    enabled_calls = {"n": 0}

    def enabled_probe():
        enabled_calls["n"] += 1
        return enabled_calls["n"] >= 2   # disabled on the first poll

    ticks = iter([0.0, 0.0, 1.0, 2.0, 3.0, 4.0])
    config = GateConfig(timeout_s=10.0, stable_for_s=0.0, poll_interval_s=1.0,
                        clock=lambda: next(ticks), sleep=lambda _s: None)
    clicked = []
    plan = ScrollPlan(locator=lambda _t: (10, 20), scroller=lambda d, a: None)
    out = act_in_view("x", clicked.append, scroll=plan,
                      enabled_probe=enabled_probe, config=config)
    assert out["acted"] is True
    assert clicked == [[10, 20]]
    assert enabled_calls["n"] >= 2       # gated until the probe reported enabled


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert "AC_act_in_view" in known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_act_in_view" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_act_in_view" in specs


def test_facade_exports():
    for name in ("act_in_view", "ScrollPlan"):
        assert hasattr(ac, name) and name in ac.__all__
