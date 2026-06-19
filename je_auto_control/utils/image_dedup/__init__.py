"""Perceptual-hash image dedupe (Pillow-based aHash/dHash, no extra deps)."""
from je_auto_control.utils.image_dedup.perceptual_hash import (
    average_hash, dedupe_images, dhash, hamming_distance, images_similar,
)

__all__ = [
    "average_hash", "dedupe_images", "dhash", "hamming_distance",
    "images_similar",
]
