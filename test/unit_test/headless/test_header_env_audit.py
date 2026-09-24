"""Regression tests for the dotenv, VEX, data-source and HTTP-header defects of the 2026-09-23 audit.

A quoted ``.env`` value kept its quotes when a comment followed, ``KEY= # c``
became the comment and a multi-line value was cut; some values did not
survive dump-then-parse. ``apply_vex`` matched products by substring (a
``requests-toolbelt`` statement hid a ``requests`` finding), ignored aliases
and let the first statement win. CSV/JSON sources kept the BOM Excel writes.
A cookie with no name was stored and a past ``Expires`` did not delete one;
``Cache-Control`` and ``Link`` split inside quotes, ``rel="NEXT"`` was not
found, and an SSE ``\\r\\n`` split across chunks dispatched an event early.
"""
import json

import pytest

from je_auto_control.utils.cookie_jar.cookie_jar import CookieJar, parse_set_cookie
from je_auto_control.utils.data_source.data_source import load_rows
from je_auto_control.utils.dotenv.dotenv import dump_dotenv, parse_dotenv
from je_auto_control.utils.http_conditional.http_conditional import parse_cache_control
from je_auto_control.utils.link_header.link_header import next_url, parse_link_header
from je_auto_control.utils.sse_client.sse_client import SSEParser
from je_auto_control.utils.vex.vex import apply_vex


@pytest.mark.parametrize("text, expected", [
    ('A="quoted" # comment', "quoted"),
    ("A='single' # comment", "single"),
    ("A= # only a comment", ""),
    ('A="line1\nline2"', "line1\nline2"),
    ('A="a\\"b" # c', 'a"b'),
])
def test_dotenv_values(text, expected):
    assert parse_dotenv(text)["A"] == expected


def test_a_multi_line_value_does_not_swallow_the_next_key():
    assert parse_dotenv('A="x\ny"\nB=2') == {"A": "x\ny", "B": "2"}


@pytest.mark.parametrize("value", ["'x'", "a\rb", 'q"q', "#h", " s ", "a\\nb"])
def test_dotenv_dump_round_trips(value):
    assert parse_dotenv(dump_dotenv({"K": value}))["K"] == value


_FINDING = [{"id": "CVE-1", "package": "requests"}]


def _vex(*statements):
    return {"statements": list(statements)}


def test_a_statement_about_another_package_does_not_suppress():
    doc = _vex({"vulnerability": {"name": "CVE-1"}, "status": "not_affected",
                "products": [{"@id": "pkg:pypi/requests-toolbelt@1.0.0"}]})
    assert apply_vex(_FINDING, doc) == _FINDING


def test_a_statement_matches_through_its_aliases():
    doc = _vex({"vulnerability": {"name": "GHSA-x", "aliases": ["CVE-1"]}, "status": "fixed"})
    assert apply_vex(_FINDING, doc) == []


def test_a_later_statement_supersedes_an_earlier_one():
    doc = _vex({"vulnerability": {"name": "CVE-1"}, "status": "under_investigation"},
               {"vulnerability": {"name": "CVE-1"}, "status": "fixed",
                "products": [{"@id": "pkg:pypi/requests@2.0"}]})
    assert apply_vex(_FINDING, doc) == []


def test_data_sources_drop_a_utf8_bom(tmp_path):
    csv_file = tmp_path / "rows.csv"
    csv_file.write_bytes("\ufeffuser,age\nann,3\n".encode("utf-8"))
    json_file = tmp_path / "rows.json"
    json_file.write_bytes(("\ufeff" + json.dumps([{"user": "bob"}])).encode("utf-8"))
    assert load_rows({"kind": "csv", "path": str(csv_file)})[0]["user"] == "ann"
    assert load_rows({"kind": "json", "path": str(json_file)})[0]["user"] == "bob"


def test_a_cookie_without_a_name_is_ignored():
    assert parse_set_cookie("=abc; Path=/") is None


def test_a_past_expires_deletes_the_cookie():
    jar = CookieJar({"sid": "abc"})
    jar.update("sid=deleted; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    assert jar.to_dict() == {}


def test_max_age_wins_over_expires():
    jar = CookieJar().update("a=1; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=60")
    assert jar.to_dict() == {"a": "1"}


def test_cache_control_keeps_a_quoted_list_together():
    directives = parse_cache_control({"Cache-Control": 'private="Set-Cookie, X-Foo", max-age=60'})
    assert directives == {"private": "Set-Cookie, X-Foo", "max-age": 60}


def test_link_relations_are_case_insensitive():
    assert next_url('<https://x/2>; rel="NEXT"') == "https://x/2"


def test_a_quoted_link_parameter_may_contain_a_semicolon():
    assert parse_link_header('<u>; title="x;y"; rel=next')[0].params["title"] == "x;y"


def test_a_crlf_split_across_chunks_is_one_line_break():
    parser = SSEParser()
    events = parser.feed("data: a\r") + parser.feed("\ndata: b\r\n\r\n")
    assert [event.data for event in events] == ["a\nb"]


def test_a_leading_bom_does_not_hide_the_first_field():
    assert [event.data for event in SSEParser().feed("\ufeffdata: x\n\n")] == ["x"]
