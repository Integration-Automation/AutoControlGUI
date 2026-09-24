"""Data-format helpers follow their specs at the edges (pure).

Binary multipart files and backslashes in filenames (RFC 7578), JSONPath
``!=`` against a missing member and ``)]`` inside a filter string (RFC 9535),
RRULE parts outside the supported subset (RFC 5545 3.3.10) and negative
values in ``LatencyDigest``.
"""
import base64

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.jsonpath.jsonpath import json_query
from je_auto_control.utils.multipart.multipart import (
    MultipartFile, build_multipart, parse_multipart,
)
from je_auto_control.utils.percentiles.percentiles import LatencyDigest
from je_auto_control.utils.recurrence.recurrence import parse_rrule


def test_a_binary_file_part_keeps_its_exact_bytes():
    raw = b"\x89PNG\xff\xfe\x00"
    parsed = parse_multipart(*build_multipart(files=[MultipartFile("f", "p.png", raw)], boundary="B"))
    part = parsed["files"][0]
    assert base64.b64decode(part["content_base64"]) == raw
    assert isinstance(part["content"], str)


def test_a_backslash_in_a_filename_round_trips():
    body = build_multipart(files=[MultipartFile("f", "a\\b.txt", b"x")], boundary="B")
    assert parse_multipart(*body)["files"][0]["filename"] == "a\\b.txt"
    escaped = (b'--B\r\nContent-Disposition: form-data; name="f"; filename="q\\"d.txt"\r\n\r\n'
               b"x\r\n--B--\r\n")
    assert parse_multipart("multipart/form-data; boundary=B", escaped)["files"][0]["filename"] == 'q"d.txt'


def test_not_equal_keeps_nodes_without_the_member():
    data = [{"k": 1}, {"k": 2}, {}]
    assert json_query(data, "$[?(@.k != 1)]") == [{"k": 2}, {}]
    assert json_query(data, "$[?(@.k == 1)]") == [{"k": 1}]
    assert json_query(data, "$[?(@.k < 5)]") == [{"k": 1}, {"k": 2}]


def test_a_filter_string_may_contain_the_closing_brackets():
    data = [{"k": "a)]"}, {"k": "b"}]
    assert json_query(data, '$[?(@.k == "a)]")]') == [{"k": "a)]"}]
    assert json_query({"a": [{"c": 1}], "b": 2}, "$.a[?(@.c)]") == [{"c": 1}]


@pytest.mark.parametrize("rule", [
    "FREQ=DAILY;BYHOUR=9,17;COUNT=4",
    "FREQ=YEARLY;BYWEEKNO=20",
    "FREQ=YEARLY;BYYEARDAY=100",
    "FREQ=DAILY;COUNT=3;UNTIL=20300101T000000Z",
])
def test_rules_outside_the_subset_are_refused(rule):
    with pytest.raises(AutoControlException):
        parse_rrule(rule)


def test_supported_rules_still_parse():
    assert parse_rrule("RRULE:FREQ=MONTHLY;BYDAY=-1FR;COUNT=3;WKST=SU").count == 3


def test_negative_values_get_their_own_buckets():
    digest = LatencyDigest()
    for value in (-100, -50, -5, 0, 7):
        digest.record(value)
    assert digest.percentile(0) == -100.0
    assert digest.percentile(40) == -50.0
    assert digest.percentile(100) == 7.0
