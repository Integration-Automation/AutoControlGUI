"""Headless tests for the idempotency-key store. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.idempotency import (
    IdempotencyConflict, IdempotencyStore, request_fingerprint,
)


def test_begin_new_then_replay():
    store = IdempotencyStore()
    first = store.begin("k1", request_fingerprint({"amount": 100}))
    assert first["status"] == "new"
    # duplicate before completion → in_progress
    assert store.begin("k1")["status"] == "in_progress"
    store.complete("k1", {"charge": "ch_1"})
    replay = store.begin("k1")
    assert replay["status"] == "completed"
    assert replay["response"] == {"charge": "ch_1"}


def test_conflict_on_different_request():
    store = IdempotencyStore()
    store.begin("k", request_fingerprint({"amount": 100}))
    with pytest.raises(IdempotencyConflict):
        store.begin("k", request_fingerprint({"amount": 999}))


def test_ttl_expiry_with_injected_clock():
    now = [1000.0]
    store = IdempotencyStore(clock=lambda: now[0], ttl=60)
    store.begin("k")
    store.complete("k", "done")
    now[0] += 120                                # past TTL
    assert store.get("k") is None
    assert store.begin("k")["status"] == "new"   # treated as fresh


def test_fingerprint_stable_and_order_independent():
    assert request_fingerprint({"a": 1, "b": 2}) == \
        request_fingerprint({"b": 2, "a": 1})
    assert request_fingerprint({"a": 1}) != request_fingerprint({"a": 2})


def test_save_load_round_trip(tmp_path):
    store = IdempotencyStore()
    store.begin("k")
    store.complete("k", {"v": 1})
    path = str(tmp_path / "idem.json")
    store.save(path)
    loaded = IdempotencyStore.load(path)
    assert loaded.begin("k")["response"] == {"v": 1}


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    name = "test-store-exec"
    rec = ac.execute_action([[
        "AC_idempotency_begin", {"name": name, "key": "o1"}]])
    assert next(v for v in rec.values()
                if isinstance(v, dict))["status"] == "new"
    ac.execute_action([[
        "AC_idempotency_complete",
        {"name": name, "key": "o1", "response": json.dumps({"ok": True})}]])
    rec2 = ac.execute_action([[
        "AC_idempotency_begin", {"name": name, "key": "o1"}]])
    out = next(v for v in rec2.values() if isinstance(v, dict))
    assert out["status"] == "completed"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_idempotency_begin", "AC_idempotency_complete"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_idempotency_begin", "ac_idempotency_complete"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_idempotency_begin", "AC_idempotency_complete"} <= specs


def test_facade_exports():
    for attr in ("IdempotencyStore", "IdempotencyConflict",
                 "request_fingerprint"):
        assert hasattr(ac, attr) and attr in ac.__all__
