"""Headless tests for the feature-flag engine. Pure stdlib, no Qt imports."""
import json

import je_auto_control as ac
from je_auto_control.utils.feature_flags import (
    FlagStore, assign_variant, evaluate_flag, is_enabled, percentage_bucket)

SPEC = {
    "flags": {
        "checkout": {
            "type": "boolean", "enabled": True,
            "variants": {"on": True, "off": False},
            "default_variant": "off", "off_variant": "off",
            "targeting": [
                {"conditions": {"country": {"op": "in", "value": ["US", "CA"]}},
                 "serve": "on"},
                {"conditions": {"plan": {"op": "eq", "value": "premium"}},
                 "serve": {"rollout": {"on": 50, "off": 50}}},
            ],
            "fallthrough": {"rollout": {"on": 10, "off": 90}},
        },
        "killed": {
            "enabled": False, "variants": {"on": True, "off": False},
            "default_variant": "on", "off_variant": "off",
        },
    }
}


def _store():
    return FlagStore.from_dict(SPEC)


def test_targeting_match():
    result = evaluate_flag(_store(), "checkout", {"country": "US"})
    assert result["value"] is True and result["reason"] == "TARGETING_MATCH"


def test_rollout_split_reason():
    result = evaluate_flag(_store(), "checkout",
                           {"plan": "premium", "targeting_key": "user1"})
    assert result["reason"] == "SPLIT" and result["variant"] in ("on", "off")


def test_fallthrough_split():
    result = evaluate_flag(_store(), "checkout", {"targeting_key": "userX"})
    assert result["reason"] == "SPLIT"


def test_kill_switch():
    result = evaluate_flag(_store(), "killed", {})
    assert result["reason"] == "DISABLED" and result["value"] is False
    assert is_enabled(_store(), "killed", {}) is False


def test_unknown_flag():
    assert evaluate_flag(_store(), "missing", {})["reason"] == "ERROR"
    assert is_enabled(_store(), "missing", {}, default=True) is True


def test_is_enabled_shortcut():
    assert is_enabled(_store(), "checkout", {"country": "CA"}) is True


def test_bucket_is_deterministic_and_in_range():
    first, second = percentage_bucket("f", "u1"), percentage_bucket("f", "u1")
    assert first == second
    assert 0 <= first < 100


def test_assign_variant_sticky_and_distributed():
    first = assign_variant("f", {"on": 50, "off": 50}, "stable")
    second = assign_variant("f", {"on": 50, "off": 50}, "stable")
    assert first == second
    on = sum(1 for i in range(2000)
             if assign_variant("f", {"on": 50, "off": 50}, f"u{i}") == "on")
    assert 850 < on < 1150          # ~50%


def test_semver_targeting():
    spec = {"flags": {"f": {
        "variants": {"on": True, "off": False}, "default_variant": "off",
        "targeting": [{"conditions": {"ver": {"op": "semver_ge",
                                              "value": "2.0.0"}}, "serve": "on"}],
    }}}
    store = FlagStore.from_dict(spec)
    assert evaluate_flag(store, "f", {"ver": "2.1.0"})["value"] is True
    assert evaluate_flag(store, "f", {"ver": "1.9.0"})["value"] is False


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_evaluate_flag",
        {"flags": json.dumps(SPEC), "key": "checkout",
         "context": json.dumps({"country": "US"})},
    ]])
    payload = next(v for v in rec.values() if isinstance(v, dict))
    assert payload["value"] is True

    rec2 = ac.execute_action([[
        "AC_flag_enabled",
        {"flags": json.dumps(SPEC), "key": "checkout",
         "context": json.dumps({"country": "CA"})},
    ]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["enabled"] is True


def test_wiring():
    assert {"AC_evaluate_flag", "AC_flag_enabled"} <= ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_evaluate_flag", "ac_flag_enabled"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_evaluate_flag", "AC_flag_enabled"} <= cmds


def test_facade_exports():
    for attr in ("FlagStore", "Flag", "evaluate_flag", "is_enabled",
                 "assign_variant", "percentage_bucket"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
