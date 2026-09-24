"""Text-processing defects from the 2026-09-24 audit.

Long phone numbers and Amex card numbers were only partly masked (or not at
all in screenshots); the email and url-credential patterns were quadratic on
crafted input; zero-width characters defeated confusable matching and text
normalisation, fullwidth Latin hid a mixed script while Japanese and Korean
were flagged as mixed, and homoglyph indices pointed at the wrong character;
isolates did not count for the base direction; fuzzy .po entries were served,
numeric escapes were not decoded and a damaged .mo raised struct.error; ICU
case bodies were compared as placeholders.
"""
import time

import pytest

from je_auto_control.utils.bidi_check.bidi_check import base_direction
from je_auto_control.utils.confusables.confusables import (
    detect_homoglyphs, is_confusable, is_mixed_script,
)
from je_auto_control.utils.gettext_catalog.gettext_catalog import parse_po, read_mo
from je_auto_control.utils.i18n_test.i18n_test import check_catalog
from je_auto_control.utils.pii_text.pii_text import detect_pii, luhn_valid, redact_pii_text
from je_auto_control.utils.redaction import rules
from je_auto_control.utils.secrets_scan.secrets_scan import scan_secrets
from je_auto_control.utils.text_normalize.text_normalize import normalize_text

ZWSP, SOFT_HYPHEN = chr(0x200B), chr(0xAD)
CYRILLIC_A = chr(0x430)


@pytest.mark.parametrize("text", ["Call +1 (555) 123-4567 now", "+44 20 7946 0958"])
def test_long_phone_numbers_are_masked_whole(text):
    redacted = redact_pii_text(text)
    assert not any(char.isdigit() for char in redacted)


def test_amex_numbers_are_cards_and_luhn_filters_random_digits():
    [finding] = detect_pii("Amex 3782 822463 10005")
    assert finding.kind == "credit_card"
    assert luhn_valid("4111 1111 1111 1111") and not luhn_valid("4111 1111 1111 1112")
    assert all(f.kind != "credit_card" for f in detect_pii("order 1234567890123"))


def test_screenshot_rules_catch_amex_and_international_phones():
    assert rules._RE_CREDIT_CARD.search("card 378282246310005 x")
    assert rules._RE_CREDIT_CARD.search("3782 822463 10005")
    assert rules._RE_PHONE.search("call +44 20 7946 0958")


@pytest.mark.parametrize("scan", [
    lambda: detect_pii("a" * 40_000),
    lambda: scan_secrets({"x": "a." * 40_000}),
])
def test_crafted_input_is_scanned_in_linear_time(scan):
    started = time.perf_counter()
    scan()
    assert time.perf_counter() - started < 1.0


def test_email_and_url_credentials_are_still_found():
    assert [f.kind for f in detect_pii("mail a.b@example.com now")] == ["email"]
    assert scan_secrets({"u": "https://user:hunter2@example.com/x"})


def test_invisible_characters_do_not_defeat_confusable_matching():
    assert is_confusable("pa" + ZWSP + "ypal", "paypal")
    assert is_confusable("p" + CYRILLIC_A + "y" + SOFT_HYPHEN + "pal", "paypal")
    assert normalize_text("pass" + ZWSP + "word") == "password"


def test_mixed_script_follows_tr39_restriction_levels():
    fullwidth = "".join(chr(0xFF41 + ord(c) - ord("a")) for c in "pypl")
    assert is_mixed_script(fullwidth[:1] + CYRILLIC_A + fullwidth[1:])
    assert not is_mixed_script("日本語のテキスト")
    assert not is_mixed_script("한국어 漢字")
    assert is_mixed_script("p" + CYRILLIC_A + "ypal")


def test_homoglyph_indices_point_into_the_input():
    text = chr(0xFB01) + "n" + CYRILLIC_A + "l"
    assert [finding["index"] for finding in detect_homoglyphs(text)] == [2]


def test_isolated_text_does_not_set_the_base_direction():
    assert base_direction(chr(0x2066) + "abc" + chr(0x2069) + " " + chr(0x5E9)) == "RTL"


def test_fuzzy_entries_are_not_translations_and_escapes_decode():
    catalog = parse_po('msgid ""\nmsgstr ""\n\n#, fuzzy\nmsgid "Save"\nmsgstr "Loeschen"\n\n'
                       'msgid "a\\101\\x41a"\nmsgstr "ok"\n')
    assert catalog.gettext("Save") == "Save"
    assert catalog.gettext("aAAa") == "ok"


@pytest.mark.parametrize("data", [b"\xde\x12\x04\x95\x00", b"\xde"])
def test_damaged_mo_data_is_a_value_error(data):
    with pytest.raises(ValueError):
        read_mo(data)


def test_icu_case_bodies_are_not_placeholders():
    base = {"k": "{g, select, male {He} other {They}} has {count} items"}
    target = {"k": "{g, select, male {Il} other {Ils}} a {count} objets"}
    report = check_catalog(base, target)
    assert report["placeholder_mismatch"] == []
    report = check_catalog(base, {"k": "{g, select, male {Il} other {Ils}} a {n} objets"})
    assert report["placeholder_mismatch"] == ["k"]
