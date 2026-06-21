"""Headless tests for config/text secret redaction. Pure stdlib, no Qt."""
import json

import je_auto_control as ac
from je_auto_control.utils.config_redaction import (
    redact_config, redact_secret_text,
)

# Build secret-shaped values at runtime so the test file itself is clean.
_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"          # matches the aws-access-key pattern
_SECRET = "hunter" + "2_long_enough_value"


def test_redact_config_masks_by_key_and_value():
    config = {"api_key": _SECRET, "creds": {"note": _AWS},
              "name": "alice", "ref": "${secrets.db}"}
    out = redact_config(config)
    assert out["api_key"] == "***"           # key-name detection
    assert out["creds"]["note"] == "***"     # aws value-format detection
    assert out["name"] == "alice"            # plain value untouched
    assert out["ref"] == "${secrets.db}"     # vault reference preserved


def test_redact_config_does_not_mutate_input():
    config = {"api_key": _SECRET}
    redact_config(config)
    assert config["api_key"] == _SECRET


def test_redact_config_lists():
    out = redact_config({"items": [{"token": _SECRET}, {"ok": "fine"}]})
    assert out["items"][0]["token"] == "***" and out["items"][1]["ok"] == "fine"


def test_custom_mask():
    out = redact_config({"secret": _SECRET}, mask="[REDACTED]")
    assert out["secret"] == "[REDACTED]"


def test_redact_text_masks_token_keeps_words():
    line = f"error: key {_AWS} was rejected"
    out = redact_secret_text(line)
    assert _AWS not in out and "***" in out
    assert "error:" in out and "rejected" in out


def test_redact_text_keeps_plain_line():
    assert redact_secret_text("just a normal log line") == \
        "just a normal log line"


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_redact_config", {"obj": json.dumps({"api_key": _SECRET})}]])
    out = next(v for v in rec.values() if isinstance(v, dict))["redacted"]
    assert out["api_key"] == "***"
    rec2 = ac.execute_action([[
        "AC_redact_secret_text", {"text": f"tok {_AWS} end"}]])
    text = next(v for v in rec2.values() if isinstance(v, dict))["text"]
    assert _AWS not in text


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_redact_config", "AC_redact_secret_text"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_redact_config", "ac_redact_secret_text"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_redact_config", "AC_redact_secret_text"} <= specs


def test_facade_exports():
    for attr in ("redact_config", "redact_secret_text"):
        assert hasattr(ac, attr) and attr in ac.__all__
