"""Headless tests for conditional HTTP requests + cache validators. No Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.http_conditional import (
    conditioned_call, is_fresh, is_not_modified, parse_cache_control,
    store_validators,
)

_RESPONSE = {
    "status": 200,
    "headers": {"ETag": '"v1"', "Last-Modified": "Wed, 21 Oct 2026 07:28:00 GMT",
                "Cache-Control": "max-age=60, public", "Date": "now"},
}


def test_parse_cache_control():
    directives = parse_cache_control({"Cache-Control": "max-age=60, no-cache"})
    assert directives["max-age"] == 60 and directives["no-cache"] is True


def test_store_validators():
    validators = store_validators(_RESPONSE)
    assert validators["etag"] == '"v1"'
    assert validators["last_modified"].endswith("GMT")
    assert validators["cache_control"]["max-age"] == 60


def test_conditioned_call_adds_headers():
    validators = store_validators(_RESPONSE)
    call = conditioned_call({"url": "https://api/x", "headers": {}}, validators)
    assert call["headers"]["If-None-Match"] == '"v1"'
    assert "If-Modified-Since" in call["headers"]


def test_is_fresh_by_age():
    validators = store_validators(_RESPONSE)
    assert is_fresh(validators, age_seconds=30) is True
    assert is_fresh(validators, age_seconds=120) is False


def test_no_store_is_never_fresh():
    validators = {"cache_control": {"no-store": True, "max-age": 999}}
    assert is_fresh(validators, age_seconds=1) is False


def test_is_not_modified():
    assert is_not_modified({"status": 304}) is True
    assert is_not_modified({"status": 200}) is False


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_parse_cache_control",
        {"headers": json.dumps({"Cache-Control": "max-age=5"})}]])
    out = next(v for v in rec.values() if isinstance(v, dict))["directives"]
    assert out["max-age"] == 5
    rec2 = ac.execute_action([[
        "AC_store_validators", {"response": json.dumps(_RESPONSE)}]])
    validators = next(v for v in rec2.values()
                      if isinstance(v, dict))["validators"]
    assert validators["etag"] == '"v1"'


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_parse_cache_control", "AC_store_validators"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_parse_cache_control", "ac_store_validators"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_parse_cache_control", "AC_store_validators"} <= specs


def test_facade_exports():
    for attr in ("parse_cache_control", "store_validators", "conditioned_call",
                 "is_fresh", "is_not_modified"):
        assert hasattr(ac, attr) and attr in ac.__all__
