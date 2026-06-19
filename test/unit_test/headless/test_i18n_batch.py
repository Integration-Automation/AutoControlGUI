"""Headless tests for the i18n/l10n batch: pseudo-localization, text-overflow
detection, and translation-catalog diffing. Pure stdlib; no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.i18n_test import (
    check_catalog, check_overflow, pseudo_localize, pseudo_localize_catalog)


# --- pseudo-localization --------------------------------------------------

def test_pseudo_localize_pads_and_preserves_placeholders():
    out = pseudo_localize("Hello {name}", expansion=0.5)
    assert out.startswith("⟦") and out.endswith("⟧")
    assert "{name}" in out                         # placeholder intact
    assert len(out) > len("Hello {name}") + 2      # padded/expanded
    assert "Hèllo" in out or "Hèllò" in out        # accented


def test_pseudo_localize_no_brackets_no_accent():
    out = pseudo_localize("OK", accent=False, brackets=False, expansion=0)
    assert out == "OK"


def test_pseudo_localize_catalog():
    cat = pseudo_localize_catalog({"a": "Save", "b": "Cancel {x}"})
    assert set(cat) == {"a", "b"}
    assert "{x}" in cat["b"]


# --- overflow detection ---------------------------------------------------

def test_check_overflow_flags_wide_text():
    elements = [
        {"text": "short", "bbox": [0, 0, 200, 20]},          # fits
        {"text": "x" * 50, "bbox": [0, 0, 40, 20]},          # overflows
        {"text": "", "bbox": [0, 0, 5, 20]},                 # no text
    ]
    issues = check_overflow(elements, avg_char_px=8.0)
    assert len(issues) == 1
    assert issues[0]["overflow_px"] > 0
    assert issues[0]["text"] == "x" * 50


# --- catalog diff ---------------------------------------------------------

def test_check_catalog_reports_problems():
    base = {"hi": "Hello {n}", "bye": "Bye", "only_base": "x"}
    target = {"hi": "Hallo", "bye": "  ", "extra": "y"}
    report = check_catalog(base, target)
    assert report["ok"] is False
    assert report["missing"] == ["only_base"]
    assert report["orphaned"] == ["extra"]
    assert report["empty"] == ["bye"]
    assert report["placeholder_mismatch"] == ["hi"]    # {n} dropped


def test_check_catalog_clean():
    report = check_catalog({"a": "A {x}"}, {"a": "Ä {x}"})
    assert report["ok"] is True


# --- wiring ---------------------------------------------------------------

def test_executor_wiring():
    rec = ac.execute_action([["AC_pseudo_localize", {"text": "Hi {x}"}]])
    assert any("{x}" in str(v) for v in rec.values())
    cat = ac.execute_action([["AC_check_catalog", {
        "base": {"a": "A"}, "target": {}}]])
    assert any("missing" in str(v) for v in cat.values())
    known = ac.executor.known_commands()
    assert {"AC_pseudo_localize", "AC_check_overflow",
            "AC_check_catalog"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_pseudo_localize", "ac_check_overflow",
            "ac_check_catalog"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_pseudo_localize", "AC_check_overflow",
            "AC_check_catalog"} <= cmds


def test_facade_exports():
    for attr in ("pseudo_localize", "pseudo_localize_catalog",
                 "check_overflow", "check_catalog"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
