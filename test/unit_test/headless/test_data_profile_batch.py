"""Headless tests for data profiling + schema inference. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.data_profile import infer_schema, profile_rows
from je_auto_control.utils.data_quality import validate_rows

_ROWS = [
    {"id": 1, "name": "alice", "age": 30},
    {"id": 2, "name": "bob", "age": 25},
    {"id": 3, "name": "alice", "age": None},
]


def test_profile_basic_columns():
    profile = profile_rows(_ROWS)
    assert profile["row_count"] == 3
    name = profile["columns"]["name"]
    assert name["inferred_type"] == "str"
    assert name["distinct"] == 2 and name["unique"] is False
    assert name["null_count"] == 0
    age = profile["columns"]["age"]
    assert age["null_count"] == 1
    assert age["null_fraction"] == 1 / 3
    assert age["min"] == 25.0 and age["max"] == 30.0


def test_profile_unique_and_top_values():
    profile = profile_rows(_ROWS)
    ident = profile["columns"]["id"]
    assert ident["unique"] is True and ident["inferred_type"] == "int"
    top = profile["columns"]["name"]["top_values"]
    assert {"value": "alice", "count": 2} in top


def test_profile_column_subset():
    profile = profile_rows(_ROWS, ["id"])
    assert list(profile["columns"]) == ["id"]


def test_infer_schema_shape():
    schema = infer_schema(_ROWS)
    assert schema["id"] == {"type": "int", "required": True, "unique": True,
                            "min": 1.0, "max": 3.0}
    assert schema["name"]["required"] is True
    assert "required" not in schema["age"]      # has a null → not required


def test_inferred_schema_validates_its_own_rows():
    schema = infer_schema(_ROWS)
    report = validate_rows(_ROWS, schema)
    assert report["ok"] is True and report["errors"] == []


def test_empty_rows():
    profile = profile_rows([])
    assert profile == {"row_count": 0, "columns": {}}
    assert infer_schema([]) == {}


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_profile_rows", {"rows": json.dumps(_ROWS)}]])
    profile = next(v for v in rec.values() if isinstance(v, dict))["profile"]
    assert profile["row_count"] == 3
    rec2 = ac.execute_action([[
        "AC_infer_schema", {"rows": json.dumps(_ROWS),
                            "columns": json.dumps(["id"])}]])
    schema = next(v for v in rec2.values() if isinstance(v, dict))["schema"]
    assert list(schema) == ["id"]


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_profile_rows", "AC_infer_schema"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_profile_rows", "ac_infer_schema"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_profile_rows", "AC_infer_schema"} <= specs


def test_facade_exports():
    for attr in ("profile_rows", "infer_schema"):
        assert hasattr(ac, attr) and attr in ac.__all__
