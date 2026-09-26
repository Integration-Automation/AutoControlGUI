"""Freshness counts the response's Age header; a repeated Cache-Control directive keeps its first value.

RFC 9111 4.2.3 makes a cached response's age include the ``Age`` it arrived
with, so a response a CDN had held for 50 s under ``max-age=60`` read as fresh
for another whole minute; 4.2.1 lets a recipient use the first of duplicate
directives, where the last one won and ``max-age=10, max-age=86400`` stayed
fresh for a day.
"""
import pytest

from je_auto_control.utils.http_conditional import (
    is_fresh, is_not_modified, parse_cache_control, store_validators,
)


def _response(**headers):
    return {"status": 200, "headers": headers}


def test_the_age_a_response_arrives_with_counts_toward_freshness():
    validators = store_validators(_response(**{"Cache-Control": "max-age=60", "Age": "50"}))
    assert validators["age"] == 50
    assert is_fresh(validators, age_seconds=5)
    assert not is_fresh(validators, age_seconds=10)


@pytest.mark.parametrize("age, expected", [("", 0), ("abc", 0), ("-5", 0), ("1.5", 0), (" 7 ", 7),
                                           ("99999999999999", 2 ** 31)])
def test_the_age_header_is_delta_seconds(age, expected):
    headers = {"Cache-Control": "max-age=60"}
    if age:
        headers["Age"] = age
    assert store_validators(_response(**headers))["age"] == expected


def test_validators_stored_before_age_was_recorded_still_work():
    assert is_fresh({"cache_control": {"max-age": 60}}, age_seconds=5)
    assert is_fresh({"cache_control": {"max-age": 60}, "age": None}, age_seconds=5)
    assert not is_fresh({"cache_control": {"max-age": 60}, "age": "junk"}, age_seconds=61)


def test_a_repeated_directive_keeps_its_first_value():
    directives = parse_cache_control({"Cache-Control": "max-age=10, max-age=86400"})
    assert directives["max-age"] == 10
    assert not is_fresh(store_validators(_response(**{"Cache-Control": "max-age=10, MAX-AGE=86400"})),
                        age_seconds=60)


@pytest.mark.parametrize("status, expected", [(304, True), ("304", True), (200, False), (None, False),
                                              ("OK", False)])
def test_is_not_modified_answers_for_any_status(status, expected):
    assert is_not_modified({"status": status}) is expected
