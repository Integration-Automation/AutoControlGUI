"""JSONPath string literals and indices follow RFC 9535.

Cases from the JSONPath compliance test suite
(jsonpath-standard/jsonpath-compliance-test-suite). Backslashes and
non-ASCII characters are built with ``chr`` so the source stays ASCII.
"""
import pytest

from je_auto_control.utils.jsonpath.jsonpath import json_query

BS = chr(92)
GRINNING_FACE = chr(0x1F600)
G_CLEF = chr(0x1D11E)


@pytest.mark.parametrize("quote", ['"', "'"])
@pytest.mark.parametrize("escapes, key", [
    (f"{BS}uD83D{BS}uDE00", GRINNING_FACE),
    (f"{BS}uD834{BS}uDD1E", G_CLEF),
    (f"{BS}u00e9", chr(0xE9)),
])
def test_a_surrogate_pair_escape_is_one_character(quote, escapes, key):
    # Each half became a lone surrogate, so the key was never found.
    assert json_query({key: "A"}, f"$[{quote}{escapes}{quote}]") == ["A"]


@pytest.mark.parametrize("escapes", [
    f"{BS}uD800", f"{BS}uDC00", f"{BS}uD800{BS}uD800", f"{BS}uD800{BS}u1234", f"{BS}uD800x", f"{BS}u12",
])
def test_an_unpaired_surrogate_or_short_escape_raises(escapes):
    with pytest.raises(ValueError):
        json_query({}, f'$["{escapes}"]')


@pytest.mark.parametrize("selector", [
    '$["a' + chr(9) + 'b"]',
    "$['a" + chr(0) + "']",
    '$["' + BS + "'" + '"]',          # an escaped single quote inside double quotes
    "$['" + BS + '"' + "']",          # an escaped double quote inside single quotes
])
def test_a_string_rfc_9535_forbids_raises(selector):
    with pytest.raises(ValueError):
        json_query({}, selector)


def test_the_quote_that_delimits_the_string_can_be_escaped():
    assert json_query({"it's": 1}, "$['it" + BS + "'s']") == [1]
    assert json_query({'say "hi"': 2}, '$["say ' + BS + '"hi' + BS + '""]') == [2]


@pytest.mark.parametrize("selector", ["$[01]", "$[-0]", "$[-01]", "$[9007199254740992]", "$[-9007199254740992]"])
def test_an_index_rfc_9535_forbids_raises(selector):
    # [01] used to select index 1 and [-0] index 0.
    with pytest.raises(ValueError):
        json_query([10, 11, 12], selector)


def test_valid_indices_still_select():
    assert json_query([10, 11, 12], "$[0]") == [10]
    assert json_query([10, 11, 12], "$[-1]") == [12]
    assert json_query([10, 11, 12], "$[9007199254740991]") == []


def test_a_non_ascii_digit_is_not_an_index():
    assert json_query([0, 1, 2, 3], f"$[{chr(0x0663)}]") == []    # Arabic-Indic three


def test_a_bald_descendant_segment_raises():
    with pytest.raises(ValueError):
        json_query({"a": 1}, "$..")
    assert json_query({"a": {"a": 1}}, "$..a") == [{"a": 1}, 1]
