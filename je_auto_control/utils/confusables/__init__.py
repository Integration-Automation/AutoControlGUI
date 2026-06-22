"""Confusable / homoglyph detection (Unicode-spoofing skeletons)."""
from je_auto_control.utils.confusables.confusables import (
    detect_homoglyphs, is_confusable, is_mixed_script, scripts_of, skeleton,
)

__all__ = [
    "detect_homoglyphs", "is_confusable", "is_mixed_script", "scripts_of",
    "skeleton",
]
