"""Spectral-residual visual saliency: map + ranked salient regions (numpy FFT)."""
from je_auto_control.utils.saliency.saliency import (
    most_salient, salient_regions, saliency_map,
)

__all__ = ["saliency_map", "salient_regions", "most_salient"]
