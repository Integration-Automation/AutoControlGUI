"""Headless tests for the environment-scoped typed asset store. Pure stdlib,
injected secret resolver for credentials; no Qt imports."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.assets import AssetStore, active_environment
from je_auto_control.utils.assets.assets import ENV_VAR


def test_typed_coercion():
    store = AssetStore()
    store.set("retries", "3", type="int")
    store.set("enabled", "yes", type="bool")
    store.set("title", "Hi", type="text")
    assert store.get("retries").value == 3
    assert store.get("enabled").value is True
    assert store.get("title").value == "Hi"


def test_environment_override_and_fallback():
    store = AssetStore()
    store.set("url", "https://default", environment="default")
    store.set("url", "https://prod", environment="prod")
    assert store.get("url", environment="prod").value == "https://prod"
    # staging not set -> falls back to default
    assert store.get("url", environment="staging").value == "https://default"
    # fallback disabled -> KeyError
    with pytest.raises(KeyError):
        store.get("url", environment="staging", fallback_to_default=False)


def test_credential_get_returns_reference_not_secret():
    store = AssetStore()
    store.set("db_pw", "vault_db_password", type="credential")
    asset = store.get("db_pw")
    assert asset.type == "credential"
    assert asset.value == "vault_db_password"     # the reference, not a secret


def test_credential_resolve_uses_injected_resolver():
    store = AssetStore(secret_resolver={"vault_db_password": "s3cr3t"}.get)
    store.set("db_pw", "vault_db_password", type="credential")
    assert store.resolve("db_pw") == "s3cr3t"
    store.set("plain", "visible", type="text")
    assert store.resolve("plain") == "visible"    # non-credential returns value


def test_resolve_without_resolver_raises():
    store = AssetStore()
    store.set("db_pw", "ref", type="credential")
    with pytest.raises(RuntimeError):
        store.resolve("db_pw")


def test_list_and_delete():
    store = AssetStore()
    store.set("a", "1", environment="dev")
    store.set("b", "2", environment="prod")
    assert {a.name for a in store.list()} == {"a", "b"}
    assert {a.name for a in store.list(environment="dev")} == {"a"}
    assert store.delete("a", environment="dev") is True
    assert store.list(environment="dev") == []


def test_persists_across_instances(tmp_path):
    db = str(tmp_path / "assets.json")
    AssetStore(db).set("token", "42", type="int", environment="prod")
    assert AssetStore(db).get("token", environment="prod").value == 42


def test_active_environment(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert active_environment() == "default"
    monkeypatch.setenv(ENV_VAR, "staging")
    assert active_environment() == "staging"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    db = str(tmp_path / "a.json")
    ac.execute_action([["AC_set_asset",
                        {"name": "n", "value": "5", "type": "int",
                         "environment": "prod", "db": db}]])
    rec = ac.execute_action([["AC_get_asset",
                              {"name": "n", "environment": "prod", "db": db}]])
    asset = next(v for v in rec.values() if isinstance(v, dict))
    assert asset["value"] == 5 and asset["type"] == "int"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_set_asset", "AC_get_asset", "AC_list_assets"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_set_asset", "ac_get_asset", "ac_list_assets"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_set_asset", "AC_get_asset", "AC_list_assets"} <= cmds


def test_facade_exports():
    for attr in ("Asset", "AssetStore", "AssetValue", "active_environment"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
