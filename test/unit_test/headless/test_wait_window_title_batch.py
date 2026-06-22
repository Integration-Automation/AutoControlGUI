"""Headless tests for wait-until-window-title. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.smart_waits import (
    WaitOutcome, wait_until_window_title,
)


def test_regex_title_appears():
    # title list flips to include a match on the 2nd poll
    state = {"polls": 0}

    def lister():
        state["polls"] += 1
        return ["Editor"] if state["polls"] < 2 else ["Shop — Checkout"]

    outcome = wait_until_window_title(r".*— Checkout$", timeout_s=5.0,
                                      poll_interval_s=0.001, title_lister=lister)
    assert isinstance(outcome, WaitOutcome) and outcome.succeeded is True


def test_substring_mode():
    outcome = wait_until_window_title(
        "Checkout", regex=False, timeout_s=5.0, poll_interval_s=0.001,
        title_lister=lambda: ["My Shop Checkout Page"])
    assert outcome.succeeded is True


def test_wait_for_vanish():
    outcome = wait_until_window_title(
        "Loading", present=False, timeout_s=5.0, poll_interval_s=0.001,
        title_lister=lambda: ["Done"])
    assert outcome.succeeded is True            # no title matches -> vanished


def test_timeout_when_never_matches():
    outcome = wait_until_window_title(
        "Nope", timeout_s=0.03, poll_interval_s=0.001,
        title_lister=lambda: ["Editor", "Browser"])
    assert outcome.succeeded is False and "timeout" in outcome.reason


def test_validation():
    for bad in ({"timeout_s": 0}, {"poll_interval_s": 0}):
        try:
            wait_until_window_title("x", title_lister=lambda: [], **bad)
        except ValueError:
            pass
        else:                                   # pragma: no cover
            raise AssertionError("expected ValueError")


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_wait_window_title" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_wait_window_title" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_wait_window_title" in specs


def test_facade_exports():
    assert hasattr(ac, "wait_until_window_title")
    assert "wait_until_window_title" in ac.__all__
