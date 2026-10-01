"""MessageFormat follows CLDR for French ordinals and locale variants, and rejects what ICU rejects."""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.message_format.message_format import (
    MessageFormatError, format_message, ordinal_category, plural_category,
)

ORDINAL_FR = "{n, selectordinal, one {#er} other {#e}}"


@pytest.mark.parametrize("n, expected", [(1, "1er"), (2, "2e"), (3, "3e"), (21, "21e"), (101, "101e")])
def test_french_ordinals_follow_cldr(n, expected):
    # French used the English ordinal rules: 21 was "21er", 2 was "two".
    assert format_message(ORDINAL_FR, {"n": n}, locale="fr") == expected
    assert ordinal_category(2, "fr") == "other"


@pytest.mark.parametrize("locale", ["fr_FR", "fr-CA", "FR", "Fr_be"])
def test_a_locale_variant_uses_its_language_rules(locale):
    assert plural_category(0, locale) == "one"
    assert plural_category(1_000_000, locale) == "many"


def test_other_locales_use_cldr_through_babel():
    pytest.importorskip("babel")
    assert plural_category(2, "ru") == "few"
    assert plural_category(5, "ru") == "many"
    assert plural_category(2, "ar") == "two"
    assert ordinal_category(2, "en_GB") == "two"


def test_an_unknown_locale_is_an_error_not_english():
    with pytest.raises(MessageFormatError):
        plural_category(2, "xx-not-a-locale")


@pytest.mark.parametrize("pattern", [
    "{n, plural, one {x}",
    "{n, plural, other {'{x}}",
    "{n, plural} tail {x}",
    "{n, plural, one x other {y}}",
    "{n, plural, one {x}}",
    "{g, select, male {he}}",
    "{n, plural, one {a} one {b} other {c}}",
    "{n, plural, one {a} offset:1 other {b}}",
    "{n, plural, =one {a} other {b}}",
    "{n, plural, offset:x other {b}}",
    "{, plural, other {x}}",
    "{a b}",
])
def test_a_pattern_icu_rejects_raises(pattern):
    with pytest.raises(MessageFormatError) as caught:
        format_message(pattern, {"n": 1, "g": "male"})
    assert isinstance(caught.value, AutoControlException) and isinstance(caught.value, ValueError)


def test_exact_selectors_compare_as_numbers():
    pattern = "{n, plural, =1.0 {exact} =2 {two} other {o}}"
    assert format_message(pattern, {"n": 1}) == "exact"
    assert format_message(pattern, {"n": 2.0}) == "two"
    assert format_message(pattern, {"n": 3}) == "o"


def test_an_infinite_value_has_a_category_but_cannot_be_rendered():
    assert plural_category(float("inf")) == "other"
    with pytest.raises(MessageFormatError):
        format_message("{n, plural, other {#}}", {"n": float("inf")})


def test_valid_patterns_still_render():
    pattern = "{n, plural, offset:1 =0 {nobody} =1 {{who}} one {{who} and # other} other {{who} and # others}}"
    assert format_message(pattern, {"n": 0, "who": "Ann"}) == "nobody"
    assert format_message(pattern, {"n": 2, "who": "Ann"}) == "Ann and 1 other"
    assert format_message(pattern, {"n": 5, "who": "Ann"}) == "Ann and 4 others"
    assert format_message("It''s '{literal}' {g, select, female {she} other {they}}", {"g": "x"}) == \
        "It's {literal} they"
