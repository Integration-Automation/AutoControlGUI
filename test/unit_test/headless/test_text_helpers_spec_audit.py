"""Text helpers follow their references at the edges (pure).

Lines split at line feeds only in diffs and merges; UTS #39 skeletons (NFKD,
map, NFD); a symmetric fuzzy score with no rapidfuzz; sentences that hold a
word (Flesch); casefolding that stays normalised (Unicode D145); the
multiplication and division signs as Common script (Scripts.txt); bidi
controls checked per paragraph (UAX #9 X8).
"""
import random

from je_auto_control.utils.bidi_check.bidi_check import is_balanced
from je_auto_control.utils.confusables.confusables import (
    detect_homoglyphs, is_confusable, is_mixed_script,
)
from je_auto_control.utils.fuzzy import fuzzy_match
from je_auto_control.utils.readability.readability import readability_stats
from je_auto_control.utils.text_diff.text_diff import (
    apply_unified, three_way_merge, unified_diff,
)
from je_auto_control.utils.text_normalize.text_normalize import normalize_text

FF, LS, CR, LF = chr(0x0C), chr(0x2028), chr(13), chr(10)


def test_a_diff_leaves_lines_it_did_not_touch_alone():
    text = f"int a;{FF}int b;{LF}int c;{LF}"
    assert apply_unified(text, "") == text
    changed = f"x='{LS}';{LF}y=2{LF}"
    source = f"x='{LS}';{LF}y=1{LF}"
    assert apply_unified(source, unified_diff(source, changed)) == changed


def test_crlf_text_keeps_its_line_endings_through_a_diff():
    source = f"a{CR}{LF}b{CR}{LF}"
    target = f"a{CR}{LF}B{CR}{LF}"
    assert apply_unified(source, unified_diff(source, target)) == target


def test_a_merge_keeps_a_form_feed_inside_a_line():
    base = f"a{FF}q{LF}r{LF}s"
    merged = three_way_merge(base, f"a{FF}q{LF}R{LF}s", f"a{FF}q{LF}r{LF}S")
    assert merged.clean and merged.text == f"a{FF}q{LF}R{LF}S"


def test_skeletons_decompose_before_and_after_mapping():
    cyrillic_e_acute = "caf" + chr(0x0435) + chr(0x0301)
    assert is_confusable(cyrillic_e_acute, "caf" + chr(0xE9))
    cyrillic_yo = chr(0x0451)
    assert not is_confusable(cyrillic_yo, "e")
    assert is_confusable(cyrillic_yo, chr(0xEB))
    assert [hit["prototype"] for hit in detect_homoglyphs(cyrillic_yo)] == ["e"]


def test_the_multiplication_and_division_signs_are_common():
    word = "".join(chr(code) for code in (0x0440, 0x0430, 0x0437, 0x043C, 0x0435, 0x0440))
    assert not is_mixed_script(word + " 3" + chr(0xD7) + "4")
    assert not is_mixed_script(word + " 8" + chr(0xF7) + "2")
    assert is_mixed_script(word + "a")


def test_the_fuzzy_fallback_is_symmetric_and_an_indel_ratio():
    similarity = fuzzy_match._similarity   # noqa: SLF001
    assert similarity("Settings", "Preferences") == similarity("Preferences", "Settings")
    assert abs(similarity("Settings", "Preferences") - 12 / 38) < 1e-9
    assert similarity("", "") == 1.0 and similarity("a", "") == 0.0
    rng = random.Random(7)
    for _ in range(300):
        left = "".join(rng.choice("abc") for _ in range(rng.randint(0, 9)))
        right = "".join(rng.choice("abc") for _ in range(rng.randint(0, 9)))
        assert similarity(left, right) == similarity(right, left)


def test_a_closing_quote_is_not_a_sentence():
    assert readability_stats('She said "Stop."')["sentences"] == 1
    assert readability_stats("One. Two! (Three?)")["sentences"] == 3


def test_casefolded_text_stays_in_its_normal_form():
    decomposed = chr(0x03AA) + chr(0x0301)
    precomposed = chr(0x0390)
    assert normalize_text(decomposed) == normalize_text(precomposed)


def test_a_paragraph_separator_ends_every_open_embedding():
    rlo, pdf = chr(0x202E), chr(0x202C)
    assert not is_balanced(f"{rlo}abc{LF}{pdf}def")
    assert is_balanced(f"{rlo}abc{pdf}{LF}def")
    assert not is_balanced(f"{rlo}abc{LF}def")
