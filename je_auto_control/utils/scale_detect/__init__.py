"""Detect the display scale / visual DPI a template renders at (per-scale profile)."""
from je_auto_control.utils.scale_detect.scale_detect import (
    detect_scale, scale_sweep,
)

__all__ = ["detect_scale", "scale_sweep"]
