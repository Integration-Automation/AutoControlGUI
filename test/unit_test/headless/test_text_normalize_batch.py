"""Headless tests for Unicode text normalisation. Pure stdlib, no Qt."""
import unicodedata

import je_auto_control as ac
from je_auto_control.utils.text_normalize import (
    deaccent, fold_whitespace, normalize_quotes, normalize_text, slugify,
)


def test_nfc_nfd_match_after_normalize():
    nfc = "Café"            # é as one code point
    nfd = "Café"          # e + combining acute
    assert nfc != nfd
    assert normalize_text(nfc) == normalize_text(nfd)
    assert normalize_text(nfc) == "café"        # casefolded, NFKC


def test_deaccent():
    assert deaccent("Café résumé naïve") == "Cafe resume naive"
    assert deaccent("") == ""


def test_fold_whitespace():
    assert fold_whitespace("  a\t b\n  c  ") == "a b c"


def test_normalize_quotes():
    assert normalize_quotes("“Hi” — it’s here…") == \
        '"Hi" - it\'s here...'


def test_normalize_text_options():
    assert normalize_text("AbC", casefold=False, collapse_ws=False) == "AbC"
    assert normalize_text("A  B") == "a b"
    # NFKC folds fullwidth/compatibility forms
    assert normalize_text("ＡＢ", casefold=False) == "AB"


def test_slugify():
    assert slugify("Café Menu! 2026") == "cafe-menu-2026"
    assert slugify("  multiple   spaces  ") == "multiple-spaces"
    assert slugify("Hello World", sep="_") == "hello_world"
    assert slugify("!!!") == ""


def test_normalize_helps_matching():
    # the canonicalisation layer fuzzy/search/OCR lack
    on_screen = normalize_text("CAFÉ")
    ocr = normalize_text(unicodedata.normalize("NFD", "café"))
    assert on_screen == ocr


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_normalize_text", {"text": "Café  Menu"}]])
    assert next(v for v in rec.values()
                if isinstance(v, dict))["text"] == "café menu"
    rec2 = ac.execute_action([["AC_slugify", {"text": "Café Menu!"}]])
    assert next(v for v in rec2.values()
                if isinstance(v, dict))["slug"] == "cafe-menu"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_normalize_text", "AC_slugify"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_normalize_text", "ac_slugify"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_normalize_text", "AC_slugify"} <= specs


def test_facade_exports():
    for attr in ("normalize_text", "deaccent", "slugify", "normalize_quotes",
                 "fold_whitespace"):
        assert hasattr(ac, attr) and attr in ac.__all__
