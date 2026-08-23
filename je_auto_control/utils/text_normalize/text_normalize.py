"""Unicode text normalisation and slug generation for robust text matching.

``fuzzy`` and ``search_index.tokenize`` only lowercase, and OCR
``find_text_matches`` only ``.lower()`` + substring — so ``"Café"`` (NFC) versus
``"Café"`` (NFD) versus OCR ``"cafe"`` compare unequal. This is the
canonicalisation layer they should run before matching.

Pure standard library (``unicodedata`` / ``re``); imports no ``PySide6``. Every
function is pure (text in, text out), so it is fully deterministic in CI.
"""
import re
import unicodedata
from typing import Literal, Tuple, cast

_QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-", "…": "...",
    " ": " ",
}
_QUOTE_TABLE = str.maketrans(_QUOTE_MAP)


_NormalForm = Literal["NFC", "NFD", "NFKC", "NFKD"]
_NORMAL_FORMS: Tuple[str, ...] = ("NFC", "NFD", "NFKC", "NFKD")


def fold_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip the ends."""
    return " ".join((text or "").split())


def deaccent(text: str) -> str:
    """Strip combining diacritical marks (``café`` -> ``cafe``)."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_quotes(text: str) -> str:
    """Replace smart quotes, dashes, ellipsis and NBSP with ASCII equivalents."""
    return (text or "").translate(_QUOTE_TABLE)


def normalize_text(text: str, *, form: str = "NFKC", casefold: bool = True,
                   collapse_ws: bool = True) -> str:
    """Canonicalise ``text``: Unicode ``form``, optional casefold + ws fold."""
    if form not in _NORMAL_FORMS:
        raise ValueError(
            f"unknown normalisation form {form!r}; "
            f"expected one of {', '.join(_NORMAL_FORMS)}")
    result = unicodedata.normalize(cast(_NormalForm, form), text or "")
    if casefold:
        result = result.casefold()
    if collapse_ws:
        result = fold_whitespace(result)
    return result


def slugify(text: str, *, sep: str = "-") -> str:
    """Produce an ASCII slug: de-accent, lowercase, join alnum runs with ``sep``."""
    base = deaccent(unicodedata.normalize("NFKC", text or "")).lower()
    slug = re.sub(r"[^a-z0-9]+", sep, base)
    return slug.strip(sep) if sep else slug
