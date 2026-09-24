"""Regression tests for the text and clipboard-format defects of the 2026-09-23 audit.

``fuzzy_ratio`` scored long near-identical texts at ~0.14 (difflib's
autojunk). ``build_rtf`` wrote unsigned / non-UTF-16 ``\\uN`` values and dropped
a lone CR; ``rtf_to_text`` skipped the fallback by character instead of token,
ignored ``\\ucN`` and left surrogate halves. A drop list with an empty path
ended early and parsing read past the terminator. Pseudo-localization broke
printf, HTML and ICU placeholders and counted padding on marker text;
``slugify`` used ``sep`` as a regex template. RTF sources are assembled from
``B`` (a backslash) so the escapes stay escapes in this file.
"""
import pytest

from je_auto_control.utils.clipboard_files.clipboard_files import build_dropfiles, parse_dropfiles
from je_auto_control.utils.clipboard_rich_formats.clipboard_rich_formats import (
    build_rtf, rows_to_csv, rtf_to_text,
)
from je_auto_control.utils.fuzzy.fuzzy_match import BACKEND, fuzzy_ratio
from je_auto_control.utils.i18n_test.i18n_test import check_catalog, pseudo_localize
from je_auto_control.utils.text_normalize.text_normalize import slugify

B = chr(92)
HANGUL, HAN, WEN, EMOJI, LEFT_QUOTE = chr(0xAC00), chr(0x4E2D), chr(0x6587), chr(0x1F600), chr(0x201C)


@pytest.mark.skipif(BACKEND != "difflib", reason="the defect was in the difflib fallback")
def test_long_near_identical_texts_score_high():
    text = "the quick brown fox jumps over the lazy dog " * 6
    assert fuzzy_ratio(text, text.replace("lazy", "lazx", 1)) > 0.99


def test_rtf_unicode_escapes_are_signed_utf16_units():
    assert build_rtf(HANGUL).endswith(B + "u-21504?}")
    assert build_rtf(EMOJI).endswith(B + "u-10179?" + B + "u-8704?}")


@pytest.mark.parametrize("text", [HANGUL, EMOJI, HAN + WEN, "a\rb", "tab\there {x} " + B])
def test_rtf_round_trips(text):
    assert rtf_to_text(build_rtf(text)) == text.replace("\r", "\n")


@pytest.mark.parametrize("source, expected", [
    ("{" + B + "rtf1" + B + "ansi " + B + "u8220" + B + "'93quoted}", LEFT_QUOTE + "quoted"),
    ("{" + B + "rtf1" + B + "uc0" + B + "u20013" + B + "u25991 ok}", HAN + WEN + "ok"),
    ("{" + B + "rtf1" + B + "uc0 " + B + "u20013 x}", HAN + "x"),
    ("{" + B + "rtf1 {" + B + "uc2 " + B + "u20013 ab}c}", HAN + "c"),
    ("{" + B + "rtf1 " + B + "u-10179?" + B + "u-8704?}", EMOJI),
])
def test_rtf_fallbacks_and_surrogates(source, expected):
    assert rtf_to_text(source) == expected


def test_a_null_cell_is_empty_in_csv():
    assert rows_to_csv([[None, 1]]) == ",1\r\n"


def test_an_empty_path_is_refused_in_a_drop_list():
    with pytest.raises(ValueError):
        build_dropfiles(["C:" + B + "a", "", "C:" + B + "b"])


def test_parsing_a_drop_list_stops_at_its_terminator():
    blob = build_dropfiles(["C:" + B + "a.txt"]) + "XY".encode("utf-16-le")
    assert parse_dropfiles(blob)["paths"] == ["C:" + B + "a.txt"]


def test_a_drop_list_offset_past_the_data_is_refused():
    blob = bytearray(build_dropfiles(["C:" + B + "a.txt"]))
    blob[0:4] = (10_000).to_bytes(4, "little")
    with pytest.raises(ValueError, match="pFiles"):
        parse_dropfiles(bytes(blob))


@pytest.mark.parametrize("placeholder", ["%(user)s", "%1$s", "%i", '<a href="/x">', "</a>", "{{x}}", "{0}"])
def test_pseudo_localize_keeps_placeholders(placeholder):
    assert placeholder in pseudo_localize(f"Save {placeholder} here")


def test_pseudo_localize_localizes_icu_cases_and_keeps_their_structure():
    out = pseudo_localize("{count, plural, one {# item} other {# items}}", brackets=False, expansion=0)
    assert out.startswith("{count, plural, one {# ") and " other {# " in out
    assert "item" not in out, "the case text is localized"


def test_padding_is_counted_on_visible_text():
    assert pseudo_localize("{very_long_placeholder_name}", expansion=1.0, brackets=False) \
        == "{very_long_placeholder_name}"


def test_check_catalog_sees_a_renamed_printf_argument():
    assert check_catalog({"k": "%(user)s"}, {"k": "%(usr)s"})["placeholder_mismatch"] == ["k"]


def test_check_catalog_allows_different_plural_categories():
    base = {"k": "{n, plural, one {# file} other {# files}}"}
    assert check_catalog(base, {"k": "{n, plural, other {# " + HAN + "}}"})["ok"]


@pytest.mark.parametrize("sep, expected", [(B, "a" + B + "b"), (B + "g<0>", "a" + B + "g<0>b"), ("x", "axb")])
def test_slugify_inserts_the_separator_literally(sep, expected):
    assert slugify("a b", sep=sep) == expected


def test_slugify_keeps_letters_that_match_the_separator():
    assert slugify("xylophone box", sep="x") == "xylophonexbox"
