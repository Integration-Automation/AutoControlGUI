"""String-distance metrics for matching short labels and OCR text.

``fuzzy`` exposes only difflib's gestalt ratio. This adds the edit-distance and
token-set metrics it lacks — Levenshtein / Damerau-Levenshtein, Jaro and
Jaro-Winkler (the standard for short names/labels), and char-n-gram Jaccard /
Dice — for better matching of typos and reordered tokens.

Pure standard library; imports no ``PySide6``. Every function is pure (two
strings in, number out), so it is fully deterministic in CI.
"""
from typing import Set

_METRICS = ("levenshtein", "damerau_levenshtein", "jaro", "jaro_winkler",
            "jaccard", "dice")


def levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance between ``a`` and ``b``."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _osa_cell(d, a, b, i, j):
    cost = 0 if a[i - 1] == b[j - 1] else 1
    value = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
        value = min(value, d[i - 2][j - 2] + 1)
    return value


def damerau_levenshtein(a: str, b: str) -> int:
    """Optimal string-alignment distance (allows adjacent transpositions)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    rows, cols = len(a) + 1, len(b) + 1
    d = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        d[i][0] = i
    for j in range(cols):
        d[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            d[i][j] = _osa_cell(d, a, b, i, j)
    return d[-1][-1]


def _match_flags(a: str, b: str, max_dist: int):
    a_match = [False] * len(a)
    b_match = [False] * len(b)
    matches = 0
    for i, char_a in enumerate(a):
        start = max(0, i - max_dist)
        end = min(i + max_dist + 1, len(b))
        for j in range(start, end):
            if not b_match[j] and char_a == b[j]:
                a_match[i] = b_match[j] = True
                matches += 1
                break
    return a_match, b_match, matches


def _transpositions(a: str, b: str, a_match, b_match) -> int:
    transposed = 0
    k = 0
    for i, flag in enumerate(a_match):
        if flag:
            while not b_match[k]:
                k += 1
            if a[i] != b[k]:
                transposed += 1
            k += 1
    return transposed // 2


def jaro(a: str, b: str) -> float:
    """Jaro similarity in ``[0, 1]``."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    max_dist = max(len(a), len(b)) // 2 - 1
    a_match, b_match, matches = _match_flags(a, b, max_dist)
    if matches == 0:
        return 0.0
    transposed = _transpositions(a, b, a_match, b_match)
    return (matches / len(a) + matches / len(b)
            + (matches - transposed) / matches) / 3


def jaro_winkler(a: str, b: str, *, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler similarity (boosts a common prefix up to 4 chars)."""
    score = jaro(a, b)
    prefix = 0
    for char_a, char_b in zip(a, b):
        if char_a != char_b or prefix >= 4:
            break
        prefix += 1
    return score + prefix * prefix_weight * (1 - score)


def _ngrams(text: str, n: int) -> Set[str]:
    text = text or ""
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def jaccard(a: str, b: str, *, n: int = 2) -> float:
    """Jaccard similarity of character ``n``-gram sets."""
    set_a, set_b = _ngrams(a, n), _ngrams(b, n)
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 1.0


def dice(a: str, b: str, *, n: int = 2) -> float:
    """Sørensen-Dice coefficient of character ``n``-gram sets."""
    set_a, set_b = _ngrams(a, n), _ngrams(b, n)
    total = len(set_a) + len(set_b)
    return 2 * len(set_a & set_b) / total if total else 1.0


def similarity(a: str, b: str, *, metric: str = "jaro_winkler") -> float:
    """Return a normalised ``[0, 1]`` similarity for ``metric``.

    Edit-distance metrics are converted to ``1 - distance / max_len``.
    """
    if metric in ("jaro", "jaro_winkler", "jaccard", "dice"):
        return globals()[metric](a, b)
    if metric in ("levenshtein", "damerau_levenshtein"):
        longest = max(len(a), len(b))
        if longest == 0:
            return 1.0
        return 1 - globals()[metric](a, b) / longest
    raise ValueError(f"unknown metric: {metric!r}; choose from {_METRICS}")
