"""Readability scoring (Flesch, Flesch-Kincaid, Gunning Fog, SMOG, ARI).

The text utilities canonicalise (``text_normalize``), match (``text_similarity``,
``fuzzy``) and rank (``search_index``) text, but nothing scores how *hard it is
to read* — there is no way to assert that an on-screen message, generated label
or doc string stays within a target reading grade. This adds the classic English
readability formulae over a deterministic tokeniser and syllable heuristic.

Pure standard library (``re`` / ``math``); imports no ``PySide6``. Every function
is pure (text in, number/report out), so it is fully deterministic in CI.
"""
import math
import re
from typing import Dict, List

_VOWELS = "aeiouy"
_WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
_SENTENCE_RE = re.compile(r"[.!?]+")


def count_syllables(word: str) -> int:
    """Estimate the syllable count of a single English ``word`` (heuristic)."""
    letters = re.sub(r"[^a-z]", "", word.lower())
    if not letters:
        return 0
    count = 0
    prev_vowel = False
    for char in letters:
        is_vowel = char in _VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    silent_e = letters.endswith("e") and not _is_consonant_le(letters)
    if silent_e and count > 1:
        count -= 1
    return max(count, 1)


def _is_consonant_le(letters: str) -> bool:
    """Whether a word ends in a sounded consonant + ``le`` (e.g. ``apple``)."""
    return (len(letters) >= 3 and letters.endswith("le")
            and letters[-3] not in _VOWELS)


def readability_stats(text: str) -> Dict[str, int]:
    """Return raw counts: ``words``, ``sentences``, ``syllables``,
    ``characters`` (letters), and ``complex_words`` (>= 3 syllables)."""
    words: List[str] = _WORD_RE.findall(text or "")
    sentences = [part for part in _SENTENCE_RE.split(text or "") if part.strip()]
    syllables = [count_syllables(word) for word in words]
    return {
        "words": len(words),
        "sentences": max(len(sentences), 1) if words else 0,
        "syllables": sum(syllables),
        "characters": sum(len(word) for word in words),
        "complex_words": sum(1 for value in syllables if value >= 3),
    }


def _safe_div(numerator: float, denominator: float) -> float:
    """Divide, returning ``0.0`` when the denominator is zero."""
    return numerator / denominator if denominator else 0.0


def flesch_reading_ease(text: str) -> float:
    """Flesch Reading Ease (higher = easier; ~0-100 for normal prose)."""
    stats = readability_stats(text)
    if not stats["words"]:
        return 0.0
    words_per_sentence = _safe_div(stats["words"], stats["sentences"])
    syllables_per_word = _safe_div(stats["syllables"], stats["words"])
    score = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    return round(score, 2)


def flesch_kincaid_grade(text: str) -> float:
    """Flesch-Kincaid US grade level."""
    stats = readability_stats(text)
    if not stats["words"]:
        return 0.0
    words_per_sentence = _safe_div(stats["words"], stats["sentences"])
    syllables_per_word = _safe_div(stats["syllables"], stats["words"])
    grade = 0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59
    return round(grade, 2)


def gunning_fog(text: str) -> float:
    """Gunning Fog index (years of formal education to understand on a read)."""
    stats = readability_stats(text)
    if not stats["words"]:
        return 0.0
    words_per_sentence = _safe_div(stats["words"], stats["sentences"])
    complex_ratio = _safe_div(stats["complex_words"], stats["words"])
    return round(0.4 * (words_per_sentence + 100 * complex_ratio), 2)


def smog_index(text: str) -> float:
    """SMOG grade (polysyllable-based, designed for >= 30-sentence samples)."""
    stats = readability_stats(text)
    if not stats["sentences"]:
        return 0.0
    scaled = stats["complex_words"] * (30.0 / stats["sentences"])
    return round(1.0430 * math.sqrt(scaled) + 3.1291, 2)


def automated_readability_index(text: str) -> float:
    """Automated Readability Index (character-based US grade level)."""
    stats = readability_stats(text)
    if not stats["words"]:
        return 0.0
    chars_per_word = _safe_div(stats["characters"], stats["words"])
    words_per_sentence = _safe_div(stats["words"], stats["sentences"])
    return round(4.71 * chars_per_word + 0.5 * words_per_sentence - 21.43, 2)


def readability_report(text: str) -> Dict[str, object]:
    """Return every metric plus the underlying counts as one report."""
    return {
        "flesch_reading_ease": flesch_reading_ease(text),
        "flesch_kincaid_grade": flesch_kincaid_grade(text),
        "gunning_fog": gunning_fog(text),
        "smog_index": smog_index(text),
        "automated_readability_index": automated_readability_index(text),
        "stats": readability_stats(text),
    }
