"""Headless tests for retrying value assertions. No Qt; clock is injected."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.expect_poll import (
    assert_poll, expect_poll, to_be_greater_than, to_be_stable, to_contain,
    to_equal, to_match_regex,
)


class _Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def _cfg():
    clock = _Clock()
    return {"timeout_s": 5.0, "interval_s": 0.25, "clock": clock.now,
            "sleep": clock.sleep}


def test_matches_after_a_few_polls():
    seq = iter([1, 3, 5, 5])
    result = expect_poll(lambda: next(seq), to_equal(5), **_cfg())
    assert result.ok and result.attempts == 3 and result.value == 5


def test_times_out_when_never_matching():
    result = expect_poll(lambda: 0, to_equal(9), **_cfg())
    assert result.ok is False and result.attempts == 21      # 20 sleeps + first


def test_contains_gt_regex_matchers():
    assert expect_poll(lambda: "done ok", to_contain("ok"), **_cfg()).ok
    assert expect_poll(lambda: 42, to_be_greater_than(10), **_cfg()).ok
    assert expect_poll(lambda: "total=42", to_match_regex(r"=\d+"), **_cfg()).ok


def test_to_be_stable_requires_repeats():
    vals = iter([7, 8, 8, 8, 8])
    # not stable until three equal in a row
    result = expect_poll(lambda: next(vals), to_be_stable(3), **_cfg())
    assert result.ok and result.value == 8


def test_assert_poll_raises_on_timeout():
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    with pytest.raises(AutoControlActionException):
        assert_poll(lambda: 0, to_equal(1), timeout_s=0)


def test_assert_poll_returns_result_on_success():
    result = assert_poll(lambda: "ready", to_equal("ready"), timeout_s=0)
    assert result.ok and result.value == "ready"


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_expect_poll" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_expect_poll" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_expect_poll" in specs


def test_executor_polls_nested_action():
    # AC_fuse_elements with no args returns {count: 0, ...} — device-free + deterministic.
    from je_auto_control.utils.executor.action_executor import _expect_poll
    result = _expect_poll(["AC_fuse_elements"], key="count", op="equals",
                          expected=0, timeout_s=0.0)
    assert result["ok"] is True and result["value"] == 0


def test_facade_exports():
    for attr in ("expect_poll", "assert_poll", "to_equal", "to_contain",
                 "to_be_stable"):
        assert hasattr(ac, attr) and attr in ac.__all__
