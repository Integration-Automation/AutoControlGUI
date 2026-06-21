"""Headless tests for the layered config resolver. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.layered_config import (
    LayeredConfig, deep_merge,
)


def test_deep_merge_recurses_and_overrides():
    base = {"db": {"host": "local", "port": 5432}, "debug": False}
    override = {"db": {"host": "prod"}, "debug": True}
    merged = deep_merge(base, override)
    assert merged == {"db": {"host": "prod", "port": 5432}, "debug": True}
    assert base["db"]["host"] == "local"      # inputs untouched


def test_priority_order_wins():
    cfg = (LayeredConfig()
           .add_layer("defaults", {"x": 1, "y": 1}, priority=0)
           .add_layer("env", {"x": 2}, priority=10))
    assert cfg.resolve() == {"x": 2, "y": 1}


def test_insertion_order_is_default_priority():
    cfg = (LayeredConfig()
           .add_layer("a", {"k": "first"})
           .add_layer("b", {"k": "second"}))
    assert cfg.resolve()["k"] == "second"     # later layer wins


def test_explain_reports_winning_layer():
    cfg = (LayeredConfig()
           .add_layer("defaults", {"db": {"host": "local", "port": 5432}})
           .add_layer("env", {"db": {"host": "prod"}}, priority=10))
    host = cfg.explain("db.host")
    assert host.value == "prod" and host.layer == "env"
    port = cfg.explain("db.port")
    assert port.value == 5432 and port.layer == "defaults"


def test_explain_unknown_key_raises():
    cfg = LayeredConfig().add_layer("a", {"x": 1})
    with pytest.raises(KeyError):
        cfg.explain("missing")


def test_get_with_default_and_layer_names():
    cfg = LayeredConfig().add_layer("a", {"x": {"y": 7}})
    assert cfg.get("x.y") == 7
    assert cfg.get("x.z", "fallback") == "fallback"
    assert cfg.layer_names() == ["a"]


# --- wiring ---------------------------------------------------------------

_LAYERS = [
    {"name": "defaults", "mapping": {"db": {"host": "local", "port": 5432}}},
    {"name": "env", "mapping": {"db": {"host": "prod"}}, "priority": 10},
]


def test_executor_resolve_and_explain():
    rec = ac.execute_action([[
        "AC_resolve_config", {"layers": json.dumps(_LAYERS)}]])
    config = next(v for v in rec.values() if isinstance(v, dict))["config"]
    assert config["db"]["host"] == "prod" and config["db"]["port"] == 5432
    rec2 = ac.execute_action([[
        "AC_explain_config", {"layers": json.dumps(_LAYERS), "key": "db.host"}]])
    trace = next(v for v in rec2.values() if isinstance(v, dict))["trace"]
    assert trace == {"key": "db.host", "value": "prod", "layer": "env"}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_resolve_config", "AC_explain_config"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_resolve_config", "ac_explain_config"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_resolve_config", "AC_explain_config"} <= specs


def test_facade_exports():
    for attr in ("LayeredConfig", "SourceTrace", "deep_merge"):
        assert hasattr(ac, attr) and attr in ac.__all__
