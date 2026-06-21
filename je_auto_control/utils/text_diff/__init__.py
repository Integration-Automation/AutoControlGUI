"""Unified-diff generation, application and three-way text merge."""
from je_auto_control.utils.text_diff.text_diff import (
    MergeResult, PatchApplyError, apply_unified, three_way_merge, unified_diff,
)

__all__ = [
    "MergeResult", "PatchApplyError", "apply_unified", "three_way_merge",
    "unified_diff",
]
