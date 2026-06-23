"""Perceptual (YIQ) image diff with anti-alias edge suppression."""
from je_auto_control.utils.perceptual_diff.perceptual_diff import (
    PerceptualDiffResult, assert_perceptual, perceptual_diff,
)

__all__ = ["PerceptualDiffResult", "assert_perceptual", "perceptual_diff"]
