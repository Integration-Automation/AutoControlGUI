"""Fuzzy string matching and dedupe (difflib by default, rapidfuzz if present)."""
from je_auto_control.utils.fuzzy.fuzzy_match import (
    BACKEND, fuzzy_best_match, fuzzy_dedupe, fuzzy_matches, fuzzy_ratio,
)

__all__ = [
    "BACKEND", "fuzzy_best_match", "fuzzy_dedupe", "fuzzy_matches",
    "fuzzy_ratio",
]
