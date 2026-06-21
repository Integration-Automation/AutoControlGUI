"""Headless tests for the bulkhead + rate-limit header parser. Pure stdlib."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.bulkhead import (
    Bulkhead, BulkheadFullError, next_delay, parse_ratelimit, parse_retry_after)
from je_auto_control.utils.exception.exceptions import AutoControlException


def test_bulkhead_permits_then_rejects():
    bulkhead = Bulkhead(2, name="api")
    assert bulkhead.try_enter() is True
    assert bulkhead.try_enter() is True
    assert bulkhead.try_enter() is False     # full
    assert bulkhead.in_flight == 2
    bulkhead.release()
    assert bulkhead.try_enter() is True


def test_bulkhead_context_manager_rejects_when_full():
    bulkhead = Bulkhead(1)
    with bulkhead:
        assert bulkhead.try_enter() is False           # full
        with pytest.raises(BulkheadFullError):
            bulkhead.run(lambda: "unreached")          # rejects on enter
    assert bulkhead.in_flight == 0                      # released after context


def test_bulkhead_run_and_bad_max():
    assert Bulkhead(1).run(lambda x: x * 2, 21) == 42
    with pytest.raises(AutoControlException):
        Bulkhead(0)


def test_retry_after_delta_and_date_and_case():
    assert parse_retry_after({"Retry-After": "120"}) == pytest.approx(120.0)
    assert parse_retry_after({"retry-after": "5"}) == pytest.approx(5.0)
    future = parse_retry_after({"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"},
                              now=0)
    assert future > 0
    assert parse_retry_after({"X": "1"}) is None


def test_parse_ratelimit():
    info = parse_ratelimit({"RateLimit-Limit": "100", "RateLimit-Remaining": "0",
                            "RateLimit-Reset": "30"})
    assert info == {"limit": 100, "remaining": 0, "reset": 30}
    assert parse_ratelimit({"X": "1"}) is None


def test_next_delay_sources():
    assert next_delay({"status": 429, "headers": {"Retry-After": "10"}}) == \
        pytest.approx(10.0)
    assert next_delay({"headers": {"RateLimit-Remaining": "0",
                                   "RateLimit-Reset": "15"}}) == pytest.approx(15.0)
    assert next_delay({"headers": {}}) == pytest.approx(0.0)


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_retry_after",
        {"response": json.dumps({"status": 429,
                                 "headers": {"Retry-After": "42"}})},
    ]])
    assert next(v for v in rec.values() if isinstance(v, dict))["delay"] == \
        pytest.approx(42.0)

    rec2 = ac.execute_action([[
        "AC_bulkhead_run",
        {"name": "t", "max_concurrent": 2,
         "actions": json.dumps([["AC_sleep", {"seconds": 0}]])},
    ]])
    payload = next(v for v in rec2.values() if isinstance(v, dict))
    assert payload["entered"] is True


def test_wiring():
    assert {"AC_bulkhead_run", "AC_retry_after"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_bulkhead_run", "ac_retry_after"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_bulkhead_run", "AC_retry_after"} <= cmds


def test_facade_exports():
    for attr in ("Bulkhead", "BulkheadFullError", "next_delay",
                 "parse_ratelimit", "parse_retry_after"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
