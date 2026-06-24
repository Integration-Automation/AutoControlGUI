"""Diff two run traces (LCS-aligned step diff: added/removed/flips/regressions)."""
from je_auto_control.utils.run_diff.run_diff import diff_runs, summarize_run_diff

__all__ = ["diff_runs", "summarize_run_diff"]
