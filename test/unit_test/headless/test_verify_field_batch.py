"""Headless tests for verify_field (pure compare + injected reader / filler)."""
import unicodedata

import je_auto_control as ac
from je_auto_control.utils.verify_field import (
    MATCH_CI, MATCH_CONTAINS, MATCH_EXACT, MATCH_NORMALIZED, MATCH_TRIM,
    compare_field_value, fill_and_verify, verify_field_value,
)


# --- pure compare ---------------------------------------------------------

def test_compare_exact():
    assert compare_field_value("abc", "abc")["match"] is True
    assert compare_field_value("abc", "abd")["match"] is False


def test_compare_trim_and_ci():
    assert compare_field_value("hi", "  hi  ", mode=MATCH_TRIM)["match"] is True
    assert compare_field_value("Hi", "hi", mode=MATCH_EXACT)["match"] is False
    assert compare_field_value("Hi", " HI ", mode=MATCH_CI)["match"] is True


def test_compare_contains():
    assert compare_field_value("ell", "Hello", mode=MATCH_CONTAINS)["match"]
    assert not compare_field_value("xyz", "Hello",
                                   mode=MATCH_CONTAINS)["match"]


def test_compare_normalized_unicode():
    # Precomposed (U+00E9) vs decomposed (e + U+0301) "cafe" differ byte-wise
    # but match once NFKC-normalized.
    base = "café"
    nfc = unicodedata.normalize("NFC", base)
    nfd = unicodedata.normalize("NFD", base)
    assert nfc != nfd
    assert compare_field_value(nfc, nfd, mode=MATCH_NORMALIZED)["match"] is True
    assert compare_field_value(nfc, nfd, mode=MATCH_EXACT)["match"] is False


def test_compare_none_is_empty():
    assert compare_field_value(None, "")["match"] is True
    assert compare_field_value("", None)["match"] is True
    result = compare_field_value("x", None)
    assert result["match"] is False
    assert result["actual"] == ""


# --- verify via injected reader -------------------------------------------

def test_verify_field_value_reads_back():
    result = verify_field_value("save.txt", reader=lambda: "save.txt")
    assert result["match"] is True
    assert result["actual"] == "save.txt"


def test_verify_field_value_mismatch():
    result = verify_field_value("save.txt", reader=lambda: "sve.txt")
    assert result["match"] is False


# --- fill_and_verify retry ------------------------------------------------

def test_fill_and_verify_succeeds_first_try():
    typed = []
    result = fill_and_verify("hello", filler=typed.append,
                             reader=lambda: "hello")
    assert result["match"] is True
    assert result["attempts"] == 1
    assert typed == ["hello"]


def test_fill_and_verify_retries_until_match():
    reads = iter(["wrong", "hello"])  # first read fails, second succeeds
    cleared = []
    typed = []
    result = fill_and_verify("hello", filler=typed.append,
                             reader=lambda: next(reads),
                             clear=lambda: cleared.append(True), attempts=3)
    assert result["match"] is True
    assert result["attempts"] == 2
    assert cleared == [True]      # cleared once before the retry
    assert typed == ["hello", "hello"]


def test_fill_and_verify_gives_up_after_attempts():
    typed = []
    result = fill_and_verify("hello", filler=typed.append,
                             reader=lambda: "nope", attempts=2)
    assert result["match"] is False
    assert result["attempts"] == 2
    assert len(typed) == 2


# --- wiring ---------------------------------------------------------------

def test_executor_pure_compare_path():
    from je_auto_control.utils.executor.action_executor import (
        _compare_field_value,
    )
    out = _compare_field_value("a b", "a  b", mode="normalized")
    assert out["match"] is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_compare_field_value", "AC_verify_field_value"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_compare_field_value", "ac_verify_field_value"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_compare_field_value", "AC_verify_field_value"} <= specs


def test_facade_exports():
    for name in ("compare_field_value", "verify_field_value",
                 "fill_and_verify"):
        assert hasattr(ac, name) and name in ac.__all__
