"""Headless tests for the background popup/interrupt watchdog.

Rules use injected matcher/action callables, so no real windows or GUI are
needed; the executor-command path uses a window rule whose matcher only
*queries* windows (and whose errors are swallowed off-Windows).
"""
import time

import je_auto_control as ac
from je_auto_control.utils.watchdog.popup_watchdog import (
    PopupWatchdog, WatchdogRule, default_popup_watchdog,
)


def test_check_once_dismisses_present_popup():
    state = {"present": True, "dismissed": 0}

    def action():
        state["dismissed"] += 1
        state["present"] = False

    w = PopupWatchdog()
    w.add_rule(WatchdogRule("dialog", lambda: state["present"], action))
    assert w.check_once() == 1
    assert state["dismissed"] == 1
    assert w.check_once() == 0          # already gone
    assert len(w.hits) == 1
    assert w.hits[0]["rule"] == "dialog"


def test_rule_error_is_swallowed():
    def boom():
        raise RuntimeError("matcher failed")

    w = PopupWatchdog()
    w.add_rule(WatchdogRule("bad", boom, lambda: None))
    assert w.check_once() == 0          # error swallowed, loop survives


def test_start_stop_lifecycle():
    state = {"n": 0}
    w = PopupWatchdog(poll_interval_s=0.02)
    w.add_rule(WatchdogRule(
        "tick", lambda: True, lambda: state.__setitem__("n", state["n"] + 1)))
    w.start()
    assert w.running is True
    time.sleep(0.15)
    w.stop()
    assert w.running is False
    assert state["n"] >= 1


def test_executor_commands():
    default_popup_watchdog.clear()
    default_popup_watchdog.stop()
    try:
        rec = ac.execute_action(
            [["AC_watchdog_add", {"title": "no-such-window-xyz",
                                  "action": "close"}]])
        assert any("rules" in str(v) for v in rec.values())
        ac.execute_action([["AC_watchdog_start"]])
        assert default_popup_watchdog.running is True
        listed = ac.execute_action([["AC_watchdog_list"]])
        assert any("running" in str(v) for v in listed.values())
    finally:
        ac.execute_action([["AC_watchdog_stop"]])
        default_popup_watchdog.clear()
    assert default_popup_watchdog.running is False


def test_facade_and_mcp_wiring():
    assert ac.default_popup_watchdog is default_popup_watchdog
    assert {"AC_watchdog_add", "AC_watchdog_start", "AC_watchdog_stop",
            "AC_watchdog_list"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_watchdog_add", "ac_watchdog_start", "ac_watchdog_stop",
            "ac_watchdog_list"} <= names


def test_builder_specs_registered():
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_watchdog_add", "AC_watchdog_start", "AC_watchdog_stop",
            "AC_watchdog_list"} <= cmds
