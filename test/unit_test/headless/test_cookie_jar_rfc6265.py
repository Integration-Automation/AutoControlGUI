"""The cookie jar follows RFC 6265 for dates, Max-Age, repeated attributes and control characters.

Date cases are from the http-state suite (abarth/http-state, ``tests/data/dates``).
"""
import datetime

import pytest

from je_auto_control.utils.cookie_jar import CookieJar, parse_set_cookie
from je_auto_control.utils.cookie_jar.cookie_jar import parse_cookie_date

UTC = datetime.timezone.utc
PAST = "Thu, 01 Jan 1970 00:00:00 GMT"


@pytest.mark.parametrize("text, expected", [
    ("Sat, 15-Apr-17 21:01:22", datetime.datetime(2017, 4, 15, 21, 1, 22, tzinfo=UTC)),
    ("Thursday, 01-Jan-1970 00:00:00 GMT", datetime.datetime(1970, 1, 1, tzinfo=UTC)),
    ("Wed, 09 Dec 2009 16:27:23 GMT", datetime.datetime(2009, 12, 9, 16, 27, 23, tzinfo=UTC)),
    ("Thu, 10 Apr 69 00:00:00 GMT", datetime.datetime(2069, 4, 10, tzinfo=UTC)),   # 0-69 is 20xx
    ("Thu, 10 Apr 70 00:00:00 GMT", datetime.datetime(1970, 4, 10, tzinfo=UTC)),
    ("Tue, 18 Oct 2011 07:42:42 +0900", datetime.datetime(2011, 10, 18, 7, 42, 42, tzinfo=UTC)),
])
def test_cookie_dates_parse_with_the_rfc_algorithm(text, expected):
    assert parse_cookie_date(text) == expected


@pytest.mark.parametrize("text", [
    "012-Aug-2008 20:49:07 GMT",          # a three-digit day is no day at all
    "Thu, 12-Aug-9999999999 20:49:07 GMT",  # raised OverflowError
    "Mon, 01 Jan 1600 00:00:00 GMT",      # before 1601
    "Wed, 31 Feb 2021 00:00:00 GMT",      # no such date
    "Wed, 01 Jan 2021 24:00:00 GMT",
    "not a date",
    "",
])
def test_an_unparseable_cookie_date_is_ignored(text):
    assert parse_cookie_date(text) is None


def test_an_unparseable_expires_leaves_the_cookie_stored():
    jar = CookieJar().update("a=b; Expires=Thu, 12-Aug-9999999999 20:49:07 GMT")
    assert jar.to_dict() == {"a": "b"}


def test_a_two_digit_year_deletes_by_the_rfc_reading():
    assert CookieJar().update("a=b; Expires=Sat, 15-Apr-17 21:01:22").to_dict() == {}


@pytest.mark.parametrize("header", [
    "a=b; Max-Age=0; Max-Age=abc",
    f"a=b; Expires={PAST}; Expires=bogus",
    "a=b; Max-Age=60; Max-Age=0",
])
def test_the_last_valid_attribute_decides_and_an_invalid_one_is_ignored(header):
    assert CookieJar().set("a", "old").update(header).to_dict() == {}


@pytest.mark.parametrize("max_age", ["+0", chr(0x0660), chr(0xFF10), "1_0", "0x1", " "])
def test_max_age_is_ascii_digits_only(max_age):
    # int() read "+0", Arabic-Indic and full-width zero as 0 (deleting) and "1_0" as 10.
    jar = CookieJar().update(f"a=b; Max-Age={max_age}")
    assert jar.to_dict() == {"a": "b"}
    assert CookieJar().update(f"a=b; Expires={PAST}; Max-Age={max_age}").to_dict() == {}


def test_a_negative_max_age_deletes():
    assert CookieJar().set("a", "1").update("a=b; Max-Age=-1").to_dict() == {}


@pytest.mark.parametrize("header", ["a=b\r\nX-Injected: 1", "a=b" + chr(0) + "c", "a=" + chr(0x7F)])
def test_a_control_character_ignores_the_whole_header(header):
    jar = CookieJar().update(header)
    assert len(jar) == 0 and parse_set_cookie(header) is None


def test_only_space_and_tab_are_trimmed():
    nbsp = chr(0xA0)
    parsed = parse_set_cookie(f"\t a =  b{nbsp}\t; Path=/ ")
    assert parsed["name"] == "a" and parsed["value"] == f"b{nbsp}"
    assert parse_set_cookie("a=b\t;\tHttpOnly")["attributes"] == {"httponly": ""}
