"""Unicode text normalisation and slug generation for AutoControl."""
from je_auto_control.utils.text_normalize.text_normalize import (
    deaccent, fold_whitespace, normalize_quotes, normalize_text, slugify,
)

__all__ = [
    "deaccent", "fold_whitespace", "normalize_quotes", "normalize_text",
    "slugify",
]
