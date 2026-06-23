"""Headless tests for soft assertions. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.soft_assert import SoftAssertions


def test_all_pass_does_not_raise():
    with SoftAssertions() as soft:
        soft.check(2 > 1, "one")
        soft.check_equal("ok", "ok")
    assert soft.passed == 2 and soft.failures == []


def test_aggregates_failures_on_exit():
    with pytest.raises(AutoControlActionException) as excinfo:
        with SoftAssertions() as soft:
            soft.check(True, "a")
            soft.check(False, "b failed")
            soft.check_equal(1, 2, "c failed")
    message = str(excinfo.value)
    assert "b failed" in message and "c failed" in message
    assert "2 soft assertion" in message


def test_check_returns_bool_and_records():
    soft = SoftAssertions(raise_on_exit=False)
    assert soft.check(True) is True
    assert soft.check(False, "nope") is False
    assert soft.passed == 1 and soft.failures == ["nope"]


def test_exit_does_not_mask_existing_exception():
    with pytest.raises(KeyError):
        with SoftAssertions() as soft:
            soft.check(False, "would-fail")
            raise KeyError("real error")        # must propagate, not aggregated


def test_manual_assert_all():
    soft = SoftAssertions(raise_on_exit=False)
    soft.check(False, "x")
    with pytest.raises(AutoControlActionException):
        soft.assert_all()


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_soft_assert" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_soft_assert" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_soft_assert" in specs


def test_executor_aggregates_checks():
    from je_auto_control.utils.executor.action_executor import _soft_assert
    result = _soft_assert([
        {"value": 5, "op": "gt", "expected": 3, "message": "five>three"},
        {"value": "abc", "op": "contains", "expected": "z", "message": "no z"},
        {"value": 0, "op": "truthy", "message": "zero falsy"}])
    assert result["ok"] is False and result["passed"] == 1
    assert "no z" in result["failures"] and "zero falsy" in result["failures"]


def test_facade_exports():
    assert hasattr(ac, "SoftAssertions") and "SoftAssertions" in ac.__all__
