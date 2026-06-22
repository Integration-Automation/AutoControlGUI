"""Headless tests for RFC 5545 recurrence expansion. Pure stdlib, no Qt."""
import datetime as dt

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.recurrence import (
    Recurrence, next_occurrence, occurrences, parse_rrule)

START = dt.datetime(2026, 1, 1, 9, 0)   # a Thursday


def _dates(rule_text, count):
    rule = parse_rrule(rule_text)
    return [m.strftime("%Y-%m-%d") for m in occurrences(rule, START, count=count)]


def test_parse_rrule_fields():
    rule = parse_rrule("RRULE:FREQ=MONTHLY;INTERVAL=2;BYDAY=2TU,-1FR;COUNT=5")
    assert isinstance(rule, Recurrence)
    assert rule.freq == "MONTHLY" and rule.interval == 2 and rule.count == 5
    assert rule.by_day == ((2, 1), (-1, 4))


def test_invalid_freq_and_byday():
    with pytest.raises(AutoControlException):
        parse_rrule("FREQ=SECONDLY")
    with pytest.raises(AutoControlException):
        parse_rrule("FREQ=DAILY;BYDAY=XX")


def test_daily_interval():
    assert _dates("FREQ=DAILY;INTERVAL=2", 3) == \
        ["2026-01-01", "2026-01-03", "2026-01-05"]


def test_weekly_byday():
    assert _dates("FREQ=WEEKLY;BYDAY=MO,WE,FR", 4) == \
        ["2026-01-02", "2026-01-05", "2026-01-07", "2026-01-09"]


def test_monthly_ordinal_weekday():
    assert _dates("FREQ=MONTHLY;BYDAY=2TU", 3) == \
        ["2026-01-13", "2026-02-10", "2026-03-10"]


def test_monthly_last_weekday_via_setpos():
    assert _dates("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", 3) == \
        ["2026-01-30", "2026-02-27", "2026-03-31"]


def test_monthly_negative_monthday():
    assert _dates("FREQ=MONTHLY;BYMONTHDAY=-1", 3) == \
        ["2026-01-31", "2026-02-28", "2026-03-31"]


def test_yearly_multiple_months():
    assert _dates("FREQ=YEARLY;BYMONTH=1,7;BYMONTHDAY=15", 4) == \
        ["2026-01-15", "2026-07-15", "2027-01-15", "2027-07-15"]


def test_until_is_inclusive_of_date():
    rule = parse_rrule("FREQ=DAILY;UNTIL=20260103")
    got = [m.strftime("%Y-%m-%d") for m in occurrences(rule, START)]
    assert got == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_count_overrides_via_param():
    rule = parse_rrule("FREQ=WEEKLY;BYDAY=MO")
    assert len(list(occurrences(rule, START, count=5))) == 5


def test_next_occurrence():
    rule = parse_rrule("FREQ=MONTHLY;BYDAY=1MO")   # first Monday
    nxt = next_occurrence(rule, START, now=dt.datetime(2026, 3, 15))
    assert nxt.strftime("%Y-%m-%d") == "2026-04-06"


def test_next_occurrence_none_when_exhausted():
    rule = parse_rrule("FREQ=DAILY;COUNT=2")
    assert next_occurrence(rule, START, now=dt.datetime(2030, 1, 1)) is None


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_rrule_occurrences",
        {"rule": "FREQ=MONTHLY;BYDAY=2TU", "dtstart": "2026-01-01T09:00:00",
         "count": 2},
    ]])
    out = next(v for v in rec.values() if isinstance(v, dict))["occurrences"]
    assert out[0].startswith("2026-01-13")

    rec2 = ac.execute_action([[
        "AC_rrule_next",
        {"rule": "FREQ=MONTHLY;BYDAY=1MO", "dtstart": "2026-01-01T09:00:00",
         "now": "2026-03-15T00:00:00"},
    ]])
    nxt = next(v for v in rec2.values() if isinstance(v, dict))["next"]
    assert nxt.startswith("2026-04-06")


def test_wiring():
    assert {"AC_rrule_occurrences", "AC_rrule_next"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_rrule_occurrences", "ac_rrule_next"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_rrule_occurrences", "AC_rrule_next"} <= cmds


def test_facade_exports():
    for attr in ("Recurrence", "parse_rrule", "occurrences", "next_occurrence"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
