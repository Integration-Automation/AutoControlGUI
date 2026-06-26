"""Simulate colour-vision deficiency and flag colours that collide under it."""
from je_auto_control.utils.cvd_simulate.cvd_simulate import (
    CVD_KINDS, color_distance, colors_collide, simulate_cvd,
)

__all__ = ["simulate_cvd", "colors_collide", "color_distance", "CVD_KINDS"]
