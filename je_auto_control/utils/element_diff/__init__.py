"""Geometry-aware element matching across frames (stable IDs, move tracking)."""
from je_auto_control.utils.element_diff.element_diff import (
    assign_stable_ids, match_elements,
)

__all__ = ["assign_stable_ids", "match_elements"]
