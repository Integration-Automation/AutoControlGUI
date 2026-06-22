"""Headless tests for confusable / homoglyph detection. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.confusables import (
    detect_homoglyphs, is_confusable, is_mixed_script, scripts_of, skeleton,
)

# "pаypal" with a Cyrillic 'а' (U+0430) in place of the second letter.
_SPOOF = "pаypal"


def test_skeleton_folds_cyrillic_and_fullwidth():
    assert skeleton(_SPOOF) == "paypal"
    assert skeleton("ａｂｃ") == "abc"   # fullwidth a b c via NFKC
    assert skeleton("paypal") == "paypal"


def test_is_confusable_requires_distinct_inputs():
    assert is_confusable(_SPOOF, "paypal") is True
    assert is_confusable("paypal", "paypal") is False   # identical -> not flagged
    assert is_confusable("apple", "orange") is False


def test_detect_homoglyphs_reports_position():
    findings = detect_homoglyphs(_SPOOF)
    assert findings == [{"index": 1, "char": "а", "prototype": "a"}]
    assert detect_homoglyphs("paypal") == []


def test_mixed_script_flag():
    assert is_mixed_script(_SPOOF) is True
    assert is_mixed_script("paypal") is False
    assert is_mixed_script("hello world 123!") is False   # COMMON ignored


def test_scripts_of_ignores_common():
    assert scripts_of(_SPOOF) == {"LATIN", "CYRILLIC"}
    assert scripts_of("123 ...") == set()


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_confusable_scan", {"text": _SPOOF}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["skeleton"] == "paypal" and out["mixed_script"] is True
    assert out["scripts"] == ["CYRILLIC", "LATIN"]
    rec2 = ac.execute_action([[
        "AC_confusable_compare", {"first": _SPOOF, "second": "paypal"}]])
    assert next(v for v in rec2.values() if isinstance(v, dict))["confusable"] is True


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_confusable_scan", "AC_confusable_compare"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_confusable_scan", "ac_confusable_compare"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_confusable_scan", "AC_confusable_compare"} <= specs


def test_facade_exports():
    for attr in ("confusable_skeleton", "is_confusable", "detect_homoglyphs",
                 "is_mixed_script", "scripts_of"):
        assert hasattr(ac, attr) and attr in ac.__all__
