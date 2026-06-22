"""Headless tests for the optimistic-concurrency versioned store. No Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.optimistic import (
    VersionConflict, VersionedStore, check_if_match, if_match_header,
)


def test_put_increments_version():
    store = VersionedStore()
    assert store.put("k", "a") == 1
    assert store.put("k", "b") == 2
    assert store.get("k") == {"value": "b", "version": 2}


def test_expected_version_guard():
    store = VersionedStore()
    store.put("k", "a")                       # version 1
    assert store.put("k", "b", expected_version=1) == 2
    with pytest.raises(VersionConflict):
        store.put("k", "c", expected_version=1)   # stale


def test_create_only_with_zero():
    store = VersionedStore()
    assert store.put("k", "a", expected_version=0) == 1
    with pytest.raises(VersionConflict):
        store.put("k", "dup", expected_version=0)   # already exists


def test_delete_guarded():
    store = VersionedStore()
    store.put("k", "a")
    with pytest.raises(VersionConflict):
        store.delete("k", expected_version=99)
    assert store.delete("k", expected_version=1) is True
    assert store.get("k") is None


def test_if_match_helpers():
    assert if_match_header(3) == '"3"'
    assert check_if_match(3, '"3"') is True
    assert check_if_match(3, '"4"') is False
    assert check_if_match(3, "*") is True


def test_save_load(tmp_path):
    store = VersionedStore()
    store.put("k", {"v": 1})
    path = str(tmp_path / "cas.json")
    store.save(path)
    assert VersionedStore.load(path).get("k")["version"] == 1


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    name = "cas-exec-test"
    rec = ac.execute_action([[
        "AC_cas_put", {"name": name, "key": "k", "value": json.dumps({"x": 1})}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["ok"] is True and out["version"] == 1
    stale = ac.execute_action([[
        "AC_cas_put", {"name": name, "key": "k", "value": "2",
                       "expected_version": 99}]])
    assert next(v for v in stale.values() if isinstance(v, dict))["ok"] is False
    rec2 = ac.execute_action([["AC_cas_get", {"name": name, "key": "k"}]])
    record = next(v for v in rec2.values() if isinstance(v, dict))["record"]
    assert record["version"] == 1


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_cas_put", "AC_cas_get"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_cas_put", "ac_cas_get"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_cas_put", "AC_cas_get"} <= specs


def test_facade_exports():
    for attr in ("VersionedStore", "VersionConflict", "check_if_match",
                 "if_match_header"):
        assert hasattr(ac, attr) and attr in ac.__all__
