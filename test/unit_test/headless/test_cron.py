"""Tests for the cron-expression parser."""
import datetime as dt

import pytest

from je_auto_control.utils.scheduler.cron import next_match, parse_cron


def test_parse_all_stars_matches_every_minute():
    expr = parse_cron("* * * * *")
    now = dt.datetime(2026, 4, 18, 12, 30)
    assert expr.matches(now)
    assert expr.matches(now.replace(minute=0))
    assert expr.matches(now.replace(hour=0, minute=0))


def test_parse_comma_list_and_step():
    expr = parse_cron("0,30 * * * *")
    assert 0 in expr.minutes and 30 in expr.minutes
    assert 15 not in expr.minutes

    every_five = parse_cron("*/5 * * * *")
    assert 0 in every_five.minutes and 55 in every_five.minutes
    assert 7 not in every_five.minutes


def test_parse_range():
    expr = parse_cron("* 9-17 * * *")
    assert expr.hours == set(range(9, 18))


def test_parse_rejects_wrong_field_count():
    with pytest.raises(ValueError):
        parse_cron("* * *")


def test_parse_rejects_out_of_range():
    with pytest.raises(ValueError):
        parse_cron("60 * * * *")


def test_parse_rejects_zero_step():
    with pytest.raises(ValueError):
        parse_cron("*/0 * * * *")


def test_next_match_rolls_to_next_hour():
    expr = parse_cron("0 * * * *")  # top of every hour
    after = dt.datetime(2026, 4, 18, 12, 30)
    nxt = next_match(expr, after)
    assert nxt == dt.datetime(2026, 4, 18, 13, 0)


def test_next_match_honours_day_of_week():
    # 2026-04-18 is a Saturday (cron dow=6); Sunday is dow=0.
    expr = parse_cron("0 9 * * 0")
    after = dt.datetime(2026, 4, 18, 8, 0)
    nxt = next_match(expr, after)
    assert nxt == dt.datetime(2026, 4, 19, 9, 0)


def test_next_match_minute_resolution_skips_same_minute():
    expr = parse_cron("30 12 * * *")
    after = dt.datetime(2026, 4, 18, 12, 30, 45)
    nxt = next_match(expr, after)
    assert nxt == dt.datetime(2026, 4, 19, 12, 30)
