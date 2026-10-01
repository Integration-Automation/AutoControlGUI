"""RRULE expansion follows RFC 5545 3.3.10 where it used to cut corners.

Expected dates were cross-checked against python-dateutil and a brute-force
reference written from the RFC text.
"""
import datetime as dt

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.recurrence.recurrence import next_occurrence, occurrences, parse_rrule


def _dates(rule, start, **kwargs):
    return [moment.date() for moment in occurrences(parse_rrule(rule), start, **kwargs)]


def test_a_yearly_ordinal_counts_within_the_year_even_with_bymonthday():
    # 1MO was the first Monday of every month; without BYMONTH it is the year's first Monday.
    assert _dates("FREQ=YEARLY;BYMONTHDAY=1;BYDAY=1MO;COUNT=4", dt.datetime(2023, 1, 1)) == [
        dt.date(2024, 1, 1), dt.date(2029, 1, 1), dt.date(2035, 1, 1), dt.date(2046, 1, 1)]


def test_with_bymonth_the_ordinal_stays_month_relative():
    assert _dates("FREQ=YEARLY;BYMONTH=5;BYMONTHDAY=1;BYDAY=1MO;COUNT=2", dt.datetime(2023, 1, 1)) == [
        dt.date(2023, 5, 1), dt.date(2028, 5, 1)]


def test_dtstart_with_microseconds_is_the_first_occurrence():
    start = dt.datetime(2024, 1, 1, 9, 0, 0, 1)
    assert list(occurrences(parse_rrule("FREQ=DAILY;COUNT=1"), start)) == [start]


def test_count_and_until_arguments_narrow_the_rule_instead_of_replacing_it():
    start = dt.datetime(2024, 1, 1)
    assert len(_dates("FREQ=DAILY;COUNT=3", start, count=10)) == 3
    assert len(_dates("FREQ=DAILY;COUNT=30", start, count=2)) == 2
    assert _dates("FREQ=DAILY;UNTIL=20240110", start, until=dt.datetime(2024, 1, 2))[-1] == dt.date(2024, 1, 2)
    assert _dates("FREQ=DAILY;UNTIL=20240102", start, until=dt.datetime(2024, 1, 9))[-1] == dt.date(2024, 1, 2)


def test_daily_applies_bysetpos_to_its_one_day_set():
    assert _dates("FREQ=DAILY;BYMONTH=1;BYSETPOS=2;COUNT=3", dt.datetime(2024, 1, 1)) == []
    assert len(_dates("FREQ=DAILY;BYMONTH=1;BYSETPOS=-1;COUNT=3", dt.datetime(2024, 1, 1))) == 3


def test_a_long_interval_is_not_cut_short():
    assert _dates("FREQ=YEARLY;INTERVAL=100;COUNT=3", dt.datetime(2000, 2, 29)) == [
        dt.date(2000, 2, 29), dt.date(2400, 2, 29), dt.date(2800, 2, 29)]
    assert len(_dates("FREQ=YEARLY;INTERVAL=401;COUNT=2", dt.datetime(2000, 1, 1))) == 2


def test_an_explicit_count_is_not_capped_by_max_iter():
    assert len(_dates("FREQ=DAILY;COUNT=150000", dt.datetime(2000, 1, 1))) == 150000


def test_next_occurrence_walks_as_far_as_now():
    rule = parse_rrule("FREQ=DAILY")
    assert next_occurrence(rule, dt.datetime(1750, 1, 1, 8), now=dt.datetime(2026, 9, 26, 12)) == \
        dt.datetime(2026, 9, 27, 8)


def test_a_rule_that_never_matches_still_ends():
    assert _dates("FREQ=MONTHLY;BYMONTH=2;BYMONTHDAY=30", dt.datetime(2024, 1, 1)) == []


@pytest.mark.parametrize("rule", [
    "FREQ=WEEKLY;BYMONTHDAY=1", "FREQ=WEEKLY;BYDAY=2MO", "FREQ=DAILY;BYDAY=-1FR", "FREQ=DAILY;WKST=XX",
    "FREQ=DAILY;UNTIL=2024-01-03",
])
def test_a_rule_rfc_5545_forbids_is_refused(rule):
    with pytest.raises(AutoControlException):
        parse_rrule(rule)


@pytest.mark.parametrize("rule, start, expected", [
    ("FREQ=DAILY;INTERVAL=9999", dt.datetime(9980, 1, 1), [dt.date(9980, 1, 1)]),
    ("FREQ=WEEKLY;INTERVAL=2000", dt.datetime(9950, 1, 1), [dt.date(9950, 1, 1), dt.date(9988, 5, 1)]),
    ("FREQ=DAILY", dt.datetime(9999, 12, 30), [dt.date(9999, 12, 30), dt.date(9999, 12, 31)]),
])
def test_the_end_of_the_calendar_ends_the_series_without_overflowing(rule, start, expected):
    # Stepping past 9999-12-31 raised OverflowError out of the executor.
    assert _dates(rule, start, max_iter=None) == expected


def test_dtstart_in_the_last_year_still_yields():
    assert _dates("FREQ=YEARLY;COUNT=2", dt.datetime(9999, 1, 1)) == [dt.date(9999, 1, 1)]


def test_a_naive_now_against_an_aware_dtstart_does_not_raise():
    start = dt.datetime(2024, 1, 1, 9, tzinfo=dt.timezone.utc)
    assert next_occurrence(parse_rrule("FREQ=DAILY"), start, now=dt.datetime(2024, 1, 5, 12)) == \
        dt.datetime(2024, 1, 6, 9, tzinfo=dt.timezone.utc)
