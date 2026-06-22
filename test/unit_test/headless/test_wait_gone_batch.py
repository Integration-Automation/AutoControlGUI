"""Headless tests for blocking wait-until-vanish. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.smart_waits import WaitOutcome, wait_until_gone


def test_returns_when_predicate_becomes_false():
    # present() is True for the first 2 polls, then False.
    calls = {"n": 0}

    def present():
        calls["n"] += 1
        return calls["n"] <= 2

    outcome = wait_until_gone(present, timeout_s=5.0, poll_interval_s=0.001)
    assert isinstance(outcome, WaitOutcome)
    assert outcome.succeeded is True
    assert outcome.reason == "target gone"
    assert outcome.samples_taken == 3


def test_already_gone_returns_immediately():
    outcome = wait_until_gone(lambda: False, timeout_s=5.0,
                              poll_interval_s=0.001)
    assert outcome.succeeded is True and outcome.samples_taken == 1


def test_timeout_when_always_present():
    outcome = wait_until_gone(lambda: True, timeout_s=0.05,
                              poll_interval_s=0.001)
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


def test_validation():
    for bad in ({"timeout_s": 0}, {"poll_interval_s": 0}, {"gone_for_s": -1}):
        try:
            wait_until_gone(lambda: False, **bad)
        except ValueError:
            pass
        else:                                  # pragma: no cover
            raise AssertionError(f"expected ValueError for {bad}")


def test_gone_for_requires_sustained_absence():
    # flips False once then True again -> must NOT count as gone with gone_for_s
    seq = iter([True, False, True, True, True, True, True, True])
    outcome = wait_until_gone(lambda: next(seq, True), timeout_s=0.05,
                              poll_interval_s=0.001, gone_for_s=10.0)
    assert outcome.succeeded is False          # never gone long enough


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_wait_image_gone", "AC_wait_text_gone"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_wait_image_gone", "ac_wait_text_gone"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_wait_image_gone", "AC_wait_text_gone"} <= specs


def test_facade_exports():
    for attr in ("wait_until_gone", "wait_until_image_gone",
                 "wait_until_text_gone"):
        assert hasattr(ac, attr) and attr in ac.__all__
