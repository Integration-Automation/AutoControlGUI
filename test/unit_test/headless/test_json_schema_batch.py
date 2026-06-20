"""Headless tests for the JSON Schema validator. Pure stdlib, no Qt imports."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException, AutoControlJsonException)
from je_auto_control.utils.json_schema import (
    SchemaValidationResult, assert_schema, is_valid, validate_json)

PERSON = {
    "type": "object",
    "required": ["name", "age"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "age": {"type": "integer", "minimum": 0, "maximum": 130},
        "roles": {"type": "array", "items": {"enum": ["admin", "user"]},
                  "uniqueItems": True},
        "email": {"type": "string", "pattern": "@"},
    },
}


def test_valid_object_passes():
    value = {"name": "Jo", "age": 30, "roles": ["admin"], "email": "a@b.com"}
    result = validate_json(value, PERSON)
    assert isinstance(result, SchemaValidationResult)
    assert result.ok is True
    assert result.errors == []
    assert is_valid(value, PERSON) is True


def test_invalid_object_collects_all_errors():
    bad = {"name": "", "age": 200, "roles": ["admin", "admin"],
           "email": "nope", "extra": 1}
    result = validate_json(bad, PERSON)
    assert result.ok is False
    keywords = {(e["path"], e["keyword"]) for e in result.errors}
    assert ("$.name", "minLength") in keywords
    assert ("$.age", "maximum") in keywords
    assert ("$.roles", "uniqueItems") in keywords
    assert ("$.email", "pattern") in keywords
    assert ("$.extra", "additionalProperties") in keywords


def test_required_property_missing():
    result = validate_json({"name": "Jo"}, PERSON)
    assert ("$", "required") in {(e["path"], e["keyword"]) for e in result.errors}


def test_integer_accepts_integral_float_but_not_bool():
    assert is_valid(5.0, {"type": "integer"}) is True
    assert is_valid(5.5, {"type": "integer"}) is False
    assert is_valid(True, {"type": "integer"}) is False
    assert is_valid(3, {"type": "number"}) is True


def test_const_keeps_bool_and_int_distinct():
    assert is_valid(True, {"const": 1}) is False
    assert is_valid(1, {"const": 1}) is True
    assert is_valid("x", {"enum": ["x", "y"]}) is True
    assert is_valid("z", {"enum": ["x", "y"]}) is False


def test_numeric_bounds_and_multiple_of():
    schema = {"type": "number", "exclusiveMinimum": 0, "multipleOf": 0.5}
    assert is_valid(1.5, schema) is True
    assert is_valid(0, schema) is False
    assert is_valid(1.3, schema) is False


def test_array_items_and_prefix_items():
    assert validate_json([1, "x"], {"prefixItems": [{"type": "integer"},
                                                    {"type": "string"}]}).errors == []
    bad = validate_json([1, 2], {"items": {"type": "string"}})
    assert bad.ok is False
    assert {e["path"] for e in bad.errors} == {"$[0]", "$[1]"}


def test_contains_and_size():
    schema = {"type": "array", "minItems": 1, "contains": {"type": "integer"}}
    assert is_valid([1, "a"], schema) is True
    assert is_valid(["a", "b"], schema) is False


def test_combinators():
    assert is_valid(5, {"oneOf": [{"type": "integer"}, {"type": "string"}]}) is True
    assert is_valid(5, {"anyOf": [{"type": "integer"}, {"type": "string"}]}) is True
    assert is_valid("s", {"not": {"type": "integer"}}) is True
    both = {"allOf": [{"type": "integer"}, {"minimum": 10}]}
    assert is_valid(5, both) is False


def test_local_ref_resolution():
    schema = {"$defs": {"pos": {"type": "integer", "minimum": 1}},
              "properties": {"n": {"$ref": "#/$defs/pos"}}}
    assert is_valid({"n": 3}, schema) is True
    bad = validate_json({"n": -1}, schema)
    assert bad.errors[0]["path"] == "$.n"
    assert bad.errors[0]["keyword"] == "minimum"


def test_unresolvable_ref_raises():
    with pytest.raises(AutoControlJsonException):
        validate_json({"n": 1}, {"properties": {"n": {"$ref": "#/$defs/missing"}}})


def test_boolean_schema():
    assert is_valid(123, True) is True
    assert is_valid(123, False) is False


def test_assert_schema_raises_on_invalid():
    with pytest.raises(AutoControlAssertionException):
        assert_schema({"age": 5}, PERSON)
    assert assert_schema({"name": "Jo", "age": 5}, PERSON) is None


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_validate_json",
        {"data": json.dumps({"name": "", "age": 1}),
         "schema": json.dumps(PERSON)},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["ok"] is False
    assert any(e["keyword"] == "minLength" for e in payload["errors"])


def test_wiring():
    assert "AC_validate_json" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_validate_json" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_validate_json" in cmds


def test_facade_exports():
    for attr in ("validate_json", "is_valid", "assert_schema",
                 "SchemaValidationResult"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
