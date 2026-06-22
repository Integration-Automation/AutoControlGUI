"""Tabular row-set diffing (CDC-style) for AutoControl data checks."""
from je_auto_control.utils.dataset_diff.dataset_diff import (
    cell_changes, diff_rows, summarize_diff,
)

__all__ = ["cell_changes", "diff_rows", "summarize_diff"]
