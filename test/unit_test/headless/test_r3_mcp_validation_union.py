"""Round-3 regression: schema validator must accept union ``type`` lists.

Several tools declare a JSON-Schema union such as ``{"type": ["string",
"array"]}``. The validator used ``_TYPE_CHECKS.get(expected)`` which raised
``TypeError: unhashable type: 'list'`` for a union, so every call to those
tools failed. These tests exercise the validator directly (no Qt, no
platform backends).
"""
import pytest

from je_auto_control.utils.mcp_server.tools._validation import (
    validate_arguments,
)


def _union_schema():
    return {
        "type": "object",
        "properties": {"key": {"type": ["string", "array"]}},
        "required": ["key"],
    }


@pytest.mark.parametrize("value", ["a string", ["a", "list"]])
def test_union_type_accepts_any_listed_type(value):
    assert validate_arguments(_union_schema(), {"key": value}) is None


def test_union_type_rejects_value_matching_no_listed_type():
    message = validate_arguments(_union_schema(), {"key": 5})
    assert message is not None
    assert "expected one of" in message
    assert "key" in message


def test_optional_union_property_when_absent_is_valid():
    schema = {
        "type": "object",
        "properties": {"params": {"type": ["array", "object"]}},
    }
    assert validate_arguments(schema, {}) is None


def test_union_including_null_accepts_none():
    schema = {
        "type": "object",
        "properties": {"pages": {"type": ["integer", "array", "null"]}},
    }
    assert validate_arguments(schema, {"pages": None}) is None
    assert validate_arguments(schema, {"pages": 3}) is None
    assert validate_arguments(schema, {"pages": "nope"}) is not None
