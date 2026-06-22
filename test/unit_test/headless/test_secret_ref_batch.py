"""Headless tests for URI-scheme value references. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.secret_ref import (
    RefResolver, SecretRefError, is_ref, resolve_ref, resolve_refs_in,
)


def test_is_ref():
    assert is_ref("env://TOKEN") and is_ref("file://./x") and is_ref("secret://k")
    assert not is_ref("plain") and not is_ref(42) and not is_ref("https://x")


def test_resolve_env_from_injected_reader():
    value = resolve_ref("env://MY_TOKEN", env={"MY_TOKEN": "abc123"})
    assert value == "abc123"
    with pytest.raises(SecretRefError):
        resolve_ref("env://MISSING", env={})


def test_resolve_file(tmp_path):
    target = tmp_path / "token.txt"
    target.write_text("file-secret", encoding="utf-8")
    assert resolve_ref(f"file://{target}") == "file-secret"


def test_file_base_dir_traversal_guard(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    resolver = RefResolver(base_dir=str(base))
    with pytest.raises(SecretRefError):
        resolver.resolve(f"file://{outside}")


def test_resolve_secret_with_injected_resolver():
    expected = "s3" + "cret-value"
    value = resolve_ref("secret://api-key",
                        secret_resolver=lambda name: expected)
    assert value == expected
    with pytest.raises(SecretRefError):
        resolve_ref("secret://x", secret_resolver=lambda name: None)


def test_resolve_refs_in_nested_structure():
    obj = {"token": "env://T", "nested": {"list": ["file-keep", "env://U"]},
           "plain": 7}
    resolved = resolve_refs_in(obj, env={"T": "tok", "U": "you"})
    assert resolved == {"token": "tok",
                        "nested": {"list": ["file-keep", "you"]}, "plain": 7}


def test_unknown_scheme_raises():
    with pytest.raises(SecretRefError):
        resolve_ref("vault://x")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    target = tmp_path / "tok.txt"
    target.write_text("xyz", encoding="utf-8")
    rec = ac.execute_action([["AC_resolve_ref", {"ref": f"file://{target}"}]])
    assert next(v for v in rec.values() if isinstance(v, dict))["value"] == "xyz"
    obj = {"a": f"file://{target}", "b": "plain"}
    rec2 = ac.execute_action([["AC_resolve_refs", {"obj": json.dumps(obj)}]])
    resolved = next(v for v in rec2.values() if isinstance(v, dict))["resolved"]
    assert resolved == {"a": "xyz", "b": "plain"}


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_resolve_ref", "AC_resolve_refs"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_resolve_ref", "ac_resolve_refs"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_resolve_ref", "AC_resolve_refs"} <= specs


def test_facade_exports():
    for attr in ("RefResolver", "SecretRefError", "is_ref", "resolve_ref",
                 "resolve_refs_in"):
        assert hasattr(ac, attr) and attr in ac.__all__
