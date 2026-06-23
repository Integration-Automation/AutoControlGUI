"""Otsu auto-thresholding for template matching (no hand-tuned min_score)."""
from je_auto_control.utils.match_autothresh.match_autothresh import (
    auto_threshold, match_auto,
)

__all__ = ["auto_threshold", "match_auto"]
