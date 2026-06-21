"""Headless tests for typed config schema validation. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.config_schema import (
    ConfigField, ConfigSchema, coerce, validate_config,
)


def test_coerce_types():
    assert coerce("8080", "int") == 8080
    assert coerce("1.5", "float") == 1.5
    assert coerce("yes", "bool") is True
    assert coerce("off", "bool") is False
    assert coerce(5, "str") == "5"


def test_validate_coerces_and_passes():
    schema = ConfigSchema({"port": ConfigField("int", required=True),
                           "debug": ConfigField("bool", default=False)})
    report = schema.validate({"port": "8080"})
    assert report["ok"] is True
    assert report["config"] == {"port": 8080, "debug": False}


def test_required_missing_is_error():
    schema = ConfigSchema({"port": ConfigField("int", required=True)})
    report = schema.validate({})
    assert report["ok"] is False
    assert report["errors"] == [{"field": "port", "error": "required"}]


def test_coercion_failure_reported():
    schema = ConfigSchema({"port": ConfigField("int")})
    report = schema.validate({"port": "not-a-number"})
    assert report["ok"] is False
    assert report["errors"][0]["error"] == "cannot coerce to int"


def test_choices_constraint():
    schema = ConfigSchema.from_dict(
        {"env": {"type": "str", "choices": ["dev", "prod"]}})
    assert schema.validate({"env": "dev"})["ok"] is True
    bad = schema.validate({"env": "staging"})
    assert bad["errors"][0]["error"] == "not an allowed choice"


def test_from_dict_and_defaults():
    report = validate_config(
        {"timeout": {"type": "float", "default": 1.0}}, {})
    assert report["config"] == {"timeout": 1.0}


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_validate_config",
        {"schema": json.dumps({"port": {"type": "int", "required": True}}),
         "config": json.dumps({"port": "9090"})}]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["ok"] is True and report["config"] == {"port": 9090}


def test_wiring():
    assert "AC_validate_config" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert "ac_validate_config" in {t.name for t in build_default_tool_registry()}
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    assert "AC_validate_config" in {s.command for s in _build_specs()}


def test_facade_exports():
    for attr in ("ConfigField", "ConfigSchema", "coerce", "validate_config"):
        assert hasattr(ac, attr) and attr in ac.__all__
