"""Headless tests for bidirectional-text QA. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.bidi_check import (
    base_direction, bidi_controls, detect_bidi_issues, has_bidi_controls,
    is_balanced, is_trojan_source, strip_bidi_controls,
)

# "value = <RLO>admin<PDF>" — a Trojan-source style reorder. Controls are built
# with chr() so this test file holds no literal bidi characters.
_RLO = chr(0x202E)
_PDF = chr(0x202C)
_LRI = chr(0x2066)
_PDI = chr(0x2069)
_LRM = chr(0x200E)
_TROJAN = f"value = {_RLO}admin{_PDF}"
_PLAIN = "value = admin"


def test_bidi_controls_lists_positions():
    found = bidi_controls(_TROJAN)
    assert [entry["name"] for entry in found] == ["RLO", "PDF"]
    assert bidi_controls(_PLAIN) == []


def test_has_controls():
    assert has_bidi_controls(_TROJAN) is True
    assert has_bidi_controls(_PLAIN) is False


def test_balance_detection():
    assert is_balanced(_TROJAN) is True               # RLO ... PDF closes
    assert is_balanced(f"{_RLO}no close") is False     # embed never closed
    assert is_balanced(_PDF) is False                  # stray close
    assert is_balanced(f"{_LRI}{_PDI}") is True         # LRI ... PDI
    assert is_balanced(f"{_RLO}{_PDI}") is False        # PDI cannot close embed


def test_base_direction():
    assert base_direction("hello") == "LTR"
    assert base_direction("אב") == "RTL"     # Hebrew alef bet
    assert base_direction("123 ...") == "NEUTRAL"


def test_strip_controls():
    assert strip_bidi_controls(_TROJAN) == _PLAIN
    assert strip_bidi_controls(_PLAIN) == _PLAIN


def test_trojan_source_flag():
    assert is_trojan_source(_TROJAN) is True
    assert is_trojan_source(_PLAIN) is False
    assert is_trojan_source(_LRM) is False             # a bare mark is benign
    assert is_trojan_source(f"{_RLO}oops") is True      # unbalanced override


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_bidi_check", {"text": _TROJAN}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["trojan_source"] is True and out["has_controls"] is True
    rec2 = ac.execute_action([["AC_bidi_strip", {"text": _TROJAN}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["text"] == _PLAIN


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_bidi_check", "AC_bidi_strip"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_bidi_check", "ac_bidi_strip"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_bidi_check", "AC_bidi_strip"} <= specs


def test_facade_exports():
    for attr in ("base_direction", "bidi_controls", "detect_bidi_issues",
                 "has_bidi_controls", "is_bidi_balanced", "is_trojan_source",
                 "strip_bidi_controls"):
        assert hasattr(ac, attr) and attr in ac.__all__
    # the report bundles everything
    assert set(detect_bidi_issues(_TROJAN)) == {
        "controls", "has_controls", "balanced", "base_direction",
        "trojan_source"}
