"""JSON Schema ``pattern`` matches with ECMA-262 meaning, and ``multipleOf`` past float range.

Cases follow the JSON-Schema-Test-Suite (draft2020-12 ``pattern``,
``patternProperties``, ``multipleOf`` and ``optional/ecmascript-regex``,
``optional/float-overflow``); the non-ASCII characters are built with
``chr`` so the source stays ASCII.
"""
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlJsonException
from je_auto_control.utils.json_schema import is_valid, validate_json
from je_auto_control.utils.json_schema.ecma_regex import compile_ecma_pattern, translate_ecma_pattern

ARABIC_INDIC_THREE = chr(0x0663)
NKO_ZERO = chr(0x07C0)
E_ACUTE = chr(0xE9)
NBSP = chr(0xA0)
ZWNBSP = chr(0xFEFF)
EM_SPACE = chr(0x2003)
LINE_SEPARATOR = chr(0x2028)
GRINNING_FACE = chr(0x1F600)


def _matches(pattern, text):
    return is_valid(text, {"type": "string", "pattern": pattern})


def test_dollar_does_not_match_before_a_trailing_newline():
    assert _matches("^[0-9]+$", "123")
    assert not _matches("^[0-9]+$", "123\n")


@pytest.mark.parametrize("pattern, text, expected", [
    (r"^\d+$", "042", True),
    (r"^\d+$", ARABIC_INDIC_THREE * 3, False),
    (r"^\D$", NKO_ZERO, True),
    (r"^\w+$", "abc_9", True),
    (r"^\w+$", E_ACUTE, False),
    (r"^\W$", E_ACUTE, True),
    (r"\bcole", "l'" + E_ACUTE + "cole", True),        # ECMA-262 \b: the e-acute is not a word character
])
def test_digit_word_and_boundary_escapes_are_ascii(pattern, text, expected):
    assert _matches(pattern, text) is expected


@pytest.mark.parametrize("text", [" ", "\t", "\v", "\f", NBSP, ZWNBSP, "\n", LINE_SEPARATOR, EM_SPACE])
def test_whitespace_is_ecma_whitespace(text):
    assert _matches(r"^\s$", text)
    assert not _matches(r"^\S$", text)
    assert _matches(r"^[\s]$", text)


def test_whitespace_classes_reject_other_characters():
    assert not _matches(r"^\s$", "\x01")
    assert _matches(r"^\S$", "a")


def test_dot_does_not_match_a_line_terminator():
    assert _matches("^a.b$", "a-b")
    assert not _matches("^a.b$", "a\rb")
    assert not _matches("^a.b$", "a" + LINE_SEPARATOR + "b")


def test_control_escapes():
    assert _matches(r"^\cC$", chr(3))
    assert _matches(r"^\cc$", chr(3))
    assert not _matches(r"^\cC$", "C")


@pytest.mark.parametrize("pattern, text, expected", [
    (r"^\p{Letter}+$", "abc" + E_ACUTE, True),
    (r"^\p{L}+$", "ab1", False),
    (r"^\p{digit}+$", "42" + ARABIC_INDIC_THREE, True),
    (r"^\p{Nd}+$", "4a", False),
    (r"^\p{gc=Lu}$", "A", True),
    (r"^\p{General_Category=Lu}$", "a", False),
    (r"^\P{L}+$", "123", True),
    (r"^[\p{L}0-9]+$", "a1" + E_ACUTE, True),
    (r"^\p{ASCII}+$", E_ACUTE, False),
    (r"^\p{Any}$", GRINNING_FACE, True),
])
def test_property_escapes(pattern, text, expected):
    assert _matches(pattern, text) is expected


@pytest.mark.parametrize("pattern", [r"\p{Script=Greek}", r"\p{NoSuchThing}", r"[\P{L}]"])
def test_an_unsupported_property_is_a_schema_error(pattern):
    with pytest.raises(AutoControlJsonException):
        _matches(pattern, "x")


def test_code_point_escapes_and_named_groups():
    assert _matches(r"^\u{1F600}$", GRINNING_FACE)
    assert _matches(r"^(?<year>\d{4})-\k<year>$", "2026-2026")
    assert not _matches(r"^(?<year>\d{4})-\k<year>$", "2026-2027")
    assert _matches(r"(?<=a)b", "ab")                   # a lookbehind stays a lookbehind


def test_the_empty_class_and_its_complement():
    assert not _matches("a[]", "a")
    assert _matches("^[^]$", "\n")
    assert _matches("^[[]$", "[")                       # ECMA-262: a literal bracket, not a nested set


def test_pattern_properties_use_the_same_semantics():
    schema = {"type": "object", "patternProperties": {r"^\d+$": {"type": "string"}}}
    assert not is_valid({"12": 3}, schema)
    assert is_valid({ARABIC_INDIC_THREE: 3}, schema)     # not ASCII digits: the key is not constrained


@pytest.mark.parametrize("pattern", ["(", "[a-", r"\p{L", 7])
def test_an_invalid_pattern_is_a_schema_error(pattern):
    with pytest.raises(AutoControlJsonException):
        validate_json("x", {"pattern": pattern})


def test_translation_leaves_plain_patterns_alone_and_is_cached():
    assert translate_ecma_pattern("^ab+c?(x|y){2}[a-z]$") == "^ab+c?(x|y){2}[a-z]" + "\\Z"
    assert compile_ecma_pattern("^a$") is compile_ecma_pattern("^a$")


@pytest.mark.parametrize("value, factor, expected", [
    (1e308, 0.123456789, False),      # the quotient overflows; round(inf) raised OverflowError
    (1e308, 0.5, True),
    (10 ** 400, 0.5, True),           # an int too large for a float
    (10 ** 400 + 1, 2.0, False),
    (1.0, 10 ** 400, False),
    (float("inf"), 0.5, False),
    (float("nan"), 0.5, False),
    (0.0075, 0.0001, True),
    (7, 2, False),
])
def test_multiple_of_past_float_range(value, factor, expected):
    assert is_valid(value, {"multipleOf": factor}) is expected
