"""Confidence-returning template matching (score, multi-scale, find-all + NMS)."""
from je_auto_control.utils.visual_match.visual_match import (
    Match, best_matches, match_masked, match_masked_all, match_template,
    match_template_all,
)

__all__ = ["Match", "best_matches", "match_masked", "match_masked_all",
           "match_template", "match_template_all"]
