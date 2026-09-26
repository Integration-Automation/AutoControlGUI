"""OTLP bytes attributes are bytesValue, and problem+json is recognised only as the media type."""
import pytest

from je_auto_control.utils.http_problem import is_problem, parse_problem
from je_auto_control.utils.otlp_export.otlp_export import attributes_to_otlp


def test_a_bytes_attribute_is_an_otlp_bytes_value():
    # It was written as the Python repr "b'\\x00\\x01'" in a stringValue.
    assert attributes_to_otlp({"raw": bytes([0, 1, 255])}) == [{"key": "raw", "value": {"bytesValue": "AAH/"}}]
    assert attributes_to_otlp({"raw": bytearray(b"hi")})[0]["value"] == {"bytesValue": "aGk="}


@pytest.mark.parametrize("content_type, expected", [
    ("application/problem+json", True),
    ("Application/Problem+JSON; charset=utf-8", True),
    (" application/problem+json ;q=1", True),
    ("text/plain; note=application/problem+json", False),
    ("application/problem+json-seq", False),
    ("application/json", False),
])
def test_only_the_problem_media_type_counts(content_type, expected):
    assert is_problem({"Content-Type": content_type}) is expected


def test_a_substring_media_type_is_not_parsed_as_a_problem():
    response = {"headers": {"content-type": "text/plain; note=application/problem+json"},
                "json": {"title": "not a problem", "status": 500}}
    assert parse_problem(response) is None
