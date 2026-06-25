"""Headless tests for JSON-Schema compatibility classification. No Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.schema_compat import (
    check_compatibility, diff_schemas, is_backward_compatible,
    is_forward_compatible, is_full_compatible,
)

_BASE = {"properties": {"id": {"type": "integer"},
                        "name": {"type": "string"}},
         "required": ["id"]}


def test_identical_is_fully_compatible():
    assert is_full_compatible(_BASE, _BASE) is True
    assert diff_schemas(_BASE, _BASE) == []


def test_added_required_breaks_backward():
    new = {"properties": {"id": {"type": "integer"},
                          "name": {"type": "string"},
                          "email": {"type": "string"}},
           "required": ["id", "email"]}
    assert is_backward_compatible(_BASE, new) is False
    assert is_forward_compatible(_BASE, new) is True
    [change] = list(check_compatibility(_BASE, new)["breaking"])
    assert change["kind"] == "field_added" and change["path"] == "email"


def test_added_optional_is_compatible_both_ways():
    new = {"properties": {"id": {"type": "integer"},
                          "name": {"type": "string"},
                          "nick": {"type": "string"}},
           "required": ["id"]}
    assert is_backward_compatible(_BASE, new) and is_forward_compatible(_BASE, new)


def test_removed_required_field_breaks_forward():
    new = {"properties": {"name": {"type": "string"}}, "required": []}
    assert is_forward_compatible(_BASE, new) is False    # id removed (was req)
    report = check_compatibility(_BASE, new, "forward")
    kinds = {c["kind"] for c in report["breaking"]}
    assert "field_removed" in kinds


def test_type_narrowed_breaks_backward():
    old = {"properties": {"v": {"type": ["integer", "string"]}}}
    new = {"properties": {"v": {"type": "integer"}}}
    assert is_backward_compatible(old, new) is False
    assert is_forward_compatible(old, new) is True
    assert diff_schemas(old, new)[0].kind == "type_narrowed"


def test_enum_value_removed_breaks_backward():
    old = {"properties": {"s": {"enum": ["a", "b", "c"]}}}
    new = {"properties": {"s": {"enum": ["a", "b"]}}}
    assert is_backward_compatible(old, new) is False
    new2 = {"properties": {"s": {"enum": ["a", "b", "c", "d"]}}}
    assert is_forward_compatible(old, new2) is False     # value added


def test_requiredness_toggle():
    relaxed = {"properties": {"id": {"type": "integer"}}, "required": []}
    assert is_forward_compatible(_BASE, relaxed) is False  # id became optional


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    new = {"properties": {"id": {"type": "integer"},
                          "email": {"type": "string"}},
           "required": ["id", "email"]}
    rec = ac.execute_action([[
        "AC_check_compatibility",
        {"old": json.dumps(_BASE), "new": json.dumps(new)}]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["compatible"] is False and report["mode"] == "backward"


def test_wiring():
    assert "AC_check_compatibility" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_check_compatibility" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_check_compatibility" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("SchemaChange", "check_compatibility", "diff_schemas",
                 "is_backward_compatible", "is_forward_compatible",
                 "is_full_compatible"):
        assert hasattr(ac, attr) and attr in ac.__all__
