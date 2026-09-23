"""JSON Schema validator defects from the 2026-09-24 audit.

An invalid ``pattern`` escaped the executor as a bare ``re.error``; a
``$ref`` cycle through a sub-schema hit ``RecursionError`` despite the cycle
detection; keywords beside ``$ref`` were ignored; ``const`` / ``enum`` let
``true`` equal ``1`` inside containers; ``multipleOf`` rounded large
integers; and ``uniqueItems`` treated ``1`` and ``1.0`` as different.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlJsonException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.json_schema.json_schema import is_valid, validate_json


@pytest.mark.parametrize("schema", [
    {"pattern": "("},
    {"patternProperties": {"(": {}}},
])
def test_an_invalid_regex_is_a_schema_error(schema):
    instance = "x" if "pattern" in schema else {"k": 1}
    with pytest.raises(AutoControlJsonException, match="invalid pattern"):
        validate_json(instance, schema)


def test_an_invalid_regex_does_not_abort_the_script():
    record = executor.execute_action([
        ["AC_validate_json", {"data": '"x"', "schema": {"pattern": "("}}],
        ["AC_validate_json", {"data": "1", "schema": {"type": "integer"}}],
    ], raise_on_error=False)
    assert len(record) == 2


def test_a_cycle_through_a_sub_schema_is_reported():
    result = validate_json(1, {"allOf": [{"$ref": "#"}]})
    assert not result.ok
    assert result.errors[0]["keyword"] == "$ref"


def test_recursive_schemas_still_validate_nested_data():
    schema = {"type": "array", "items": {"anyOf": [{"type": "integer"}, {"$ref": "#"}]}}
    assert is_valid([1, [2, [3]]], schema)
    assert not is_valid([1, [2, ["x"]]], schema)


def test_keywords_beside_a_ref_apply():
    schema = {"$defs": {"s": {"type": "string"}}, "$ref": "#/$defs/s", "maxLength": 3}
    assert is_valid("abc", schema)
    assert not is_valid("toolong", schema)
    assert not is_valid(5, schema)


@pytest.mark.parametrize("instance, schema", [
    ({"a": True}, {"const": {"a": 1}}),
    ([True], {"enum": [[1]]}),
    ([0], {"const": [False]}),
])
def test_booleans_stay_distinct_from_numbers_inside_containers(instance, schema):
    assert not is_valid(instance, schema)


def test_equal_containers_still_match():
    assert is_valid({"a": [1, {"b": None}]}, {"const": {"a": [1, {"b": None}]}})


def test_multiple_of_is_exact_for_integers():
    assert not is_valid(10**17 + 1, {"multipleOf": 2})
    assert is_valid(10**17, {"multipleOf": 2})
    assert is_valid(0.3, {"multipleOf": 0.1})


def test_unique_items_treats_one_and_one_point_zero_as_equal():
    assert not is_valid([1, 1.0], {"uniqueItems": True})
    assert not is_valid([{"a": 2}, {"a": 2.0}], {"uniqueItems": True})
    assert is_valid([1, True], {"uniqueItems": True})
