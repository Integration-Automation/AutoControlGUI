"""Headless tests for the data-quality batch: row schema validation,
field extraction, and masking. Pure stdlib; no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.data_quality import (
    extract_fields, mask_rows, validate_rows)


# --- validate_rows --------------------------------------------------------

def test_validate_rows_reports_errors():
    rows = [
        {"name": "Ada", "age": 36, "email": "ada@x.io"},
        {"name": "", "age": 200, "email": "nope"},
        {"name": "Bo", "age": 41, "email": "bo@y.io"},
    ]
    schema = {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "min": 0, "max": 130},
        "email": {"regex": r".+@.+\..+"},
    }
    report = validate_rows(rows, schema)
    assert report["ok"] is False
    assert report["valid_count"] == 2 and report["invalid_count"] == 1
    fields = {e["field"] for e in report["errors"] if e["row"] == 1}
    assert {"name", "age", "email"} <= fields


def test_validate_rows_unique_and_allowed():
    rows = [{"id": "a", "tier": "gold"}, {"id": "a", "tier": "bronze"}]
    schema = {"id": {"unique": True},
              "tier": {"allowed": ["gold", "silver"]}}
    report = validate_rows(rows, schema)
    errors = {(e["row"], e["field"], e["error"]) for e in report["errors"]}
    assert (1, "id", "duplicate") in errors
    assert (1, "tier", "not in allowed set") in errors


def test_validate_rows_all_valid():
    report = validate_rows([{"n": 5}], {"n": {"type": "int", "min": 1}})
    assert report["ok"] is True and report["invalid_count"] == 0


# --- extract_fields -------------------------------------------------------

def test_extract_presets_and_custom():
    text = "Mail ada@x.io or see https://x.io — ref #A12 on 2026-06-19."
    out = extract_fields(text, fields=["email", "url", "date_iso"])
    assert out["email"] == ["ada@x.io"]
    assert out["url"] == ["https://x.io"]
    assert out["date_iso"] == ["2026-06-19"]
    custom = extract_fields(text, fields=[], patterns={"ref": r"#[A-Z]\d+"})
    assert custom["ref"] == ["#A12"]


# --- mask_rows ------------------------------------------------------------

def test_mask_modes():
    rows = [{"name": "Ada", "ssn": "123456789", "tok": "secret"}]
    masked = mask_rows(rows, {"ssn": "partial", "tok": "redact",
                              "name": "hash"})
    assert masked[0]["ssn"] == "*****6789"
    assert masked[0]["tok"] == "***"
    assert len(masked[0]["name"]) == 64        # sha256 hex
    assert rows[0]["name"] == "Ada"            # original untouched


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    rec = ac.execute_action([["AC_validate_rows", {
        "rows": [{"n": 1}], "schema": {"n": {"type": "int"}}}]])
    assert any("'ok': True" in str(v) for v in rec.values())
    ex = ac.execute_action([["AC_extract_fields", {
        "text": "a@b.co", "fields": ["email"]}]])
    assert any("a@b.co" in str(v) for v in ex.values())
    known = ac.executor.known_commands()
    assert {"AC_validate_rows", "AC_extract_fields", "AC_mask_rows"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_validate_rows", "ac_extract_fields", "ac_mask_rows"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_validate_rows", "AC_extract_fields", "AC_mask_rows"} <= cmds


def test_facade_exports():
    for attr in ("validate_rows", "extract_fields", "mask_rows"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
