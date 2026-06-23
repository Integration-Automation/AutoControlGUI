"""Rotation- and scale-tolerant template matching (scale-space x angle sweep)."""
from je_auto_control.utils.rotated_match.rotated_match import (
    RotatedMatch, match_rotated, match_rotated_all, scale_space,
)

__all__ = ["RotatedMatch", "match_rotated", "match_rotated_all", "scale_space"]
