"""Grade the legibility of on-screen text by sampling its actual colours."""
from je_auto_control.utils.contrast_map.contrast_map import (
    dominant_pair, grade_contrast, region_contrast,
)

__all__ = ["grade_contrast", "dominant_pair", "region_contrast"]
