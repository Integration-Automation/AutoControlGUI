"""PIL-only golden-image comparison for visual regression tests."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw


@dataclass(frozen=True)
class MaskRegion:
    """Rectangular area to exclude from the comparison (animated banners etc.)."""
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class DiffResult:
    """Outcome of one ``compare_to_golden`` call.

    ``matched`` is the final pass/fail. ``diff_pct`` is the percentage
    of pixels that differ beyond ``per_pixel_threshold``. ``diff_image``
    is a copy of the actual image with mismatched pixels highlighted —
    persist it with :meth:`write_diff` for the failure artifact.
    """
    matched: bool
    diff_pct: float
    differing_pixels: int
    total_pixels: int
    tolerance_pct: float
    per_pixel_threshold: int
    diff_image: Optional[Image.Image] = field(default=None, repr=False)

    @property
    def summary(self) -> str:
        return (
            f"visual_regression: {self.diff_pct:.3f}% differ "
            f"(>{self.tolerance_pct:.3f}% allowed), "
            f"{self.differing_pixels}/{self.total_pixels} pixels"
        )

    def write_diff(self, path) -> Path:
        """Persist the diff overlay; idempotent — returns the target path."""
        target = Path(os.path.expanduser(str(path)))
        if self.diff_image is None:
            raise RuntimeError("no diff image available")
        target.parent.mkdir(parents=True, exist_ok=True)
        self.diff_image.save(str(target))
        return target


def _expand_path(path) -> Path:
    return Path(os.path.expanduser(str(path)))


def _apply_masks(image: Image.Image,
                 masks: Sequence[MaskRegion]) -> Image.Image:
    """Black out the masked regions on a *copy* so the input stays intact."""
    if not masks:
        return image
    result = image.copy()
    draw = ImageDraw.Draw(result)
    for m in masks:
        draw.rectangle(
            (m.left, m.top, m.right, m.bottom), fill=(0, 0, 0),
        )
    return result


def take_golden(path,
                *, source: Optional[Image.Image] = None,
                region: Optional[Sequence[int]] = None) -> Path:
    """Capture and save a golden image.

    ``source`` overrides the live screen grab (handy for unit tests).
    ``region`` is ``(x, y, width, height)``; passed through to ``ImageGrab``.
    """
    target = _expand_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = source if source is not None else _grab(region)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(str(target))
    return target


def _grab(region: Optional[Sequence[int]]) -> Image.Image:
    """Screen capture via PIL.ImageGrab; raises if not available."""
    from PIL import ImageGrab
    if region is not None:
        x, y, width, height = (int(v) for v in region)
        return ImageGrab.grab(bbox=(x, y, x + width, y + height),
                              all_screens=True)
    return ImageGrab.grab(all_screens=True)


def image_difference(actual: Image.Image, expected: Image.Image,
                     *, per_pixel_threshold: int = 16,
                     masks: Sequence[MaskRegion] = (),
                     ) -> Tuple[int, int, Image.Image]:
    """Per-pixel diff returning ``(differing, total, overlay)``.

    A pixel counts as different when the max RGB channel delta exceeds
    ``per_pixel_threshold`` (so JPEG quantisation noise doesn't trip
    the comparison). ``masks`` blacks out those regions on *both* sides
    before comparing.
    """
    if actual.size != expected.size:
        raise ValueError(
            f"image sizes differ: actual={actual.size}, "
            f"expected={expected.size}"
        )
    if actual.mode != "RGB":
        actual = actual.convert("RGB")
    if expected.mode != "RGB":
        expected = expected.convert("RGB")
    a = _apply_masks(actual, masks)
    e = _apply_masks(expected, masks)
    diff = ImageChops.difference(a, e)
    overlay = a.copy()
    overlay_draw = ImageDraw.Draw(overlay)
    differing = 0
    diff_data = diff.load()
    threshold = max(0, int(per_pixel_threshold))
    width, height = diff.size
    for y in range(height):
        for x in range(width):
            r, g, b = diff_data[x, y][:3]
            if max(r, g, b) > threshold:
                differing += 1
                overlay_draw.point((x, y), fill=(255, 0, 0))
    total = width * height
    return differing, total, overlay


def compare_to_golden(golden_path,
                      *, actual: Optional[Image.Image] = None,
                      region: Optional[Sequence[int]] = None,
                      tolerance: float = 0.0,
                      per_pixel_threshold: int = 16,
                      masks: Sequence[MaskRegion] = (),
                      ) -> DiffResult:
    """Compare a fresh capture against a saved golden image.

    ``tolerance`` is the percentage of pixels allowed to differ (so
    a tiny rendering wobble doesn't fail every CI run). Defaults to
    ``0.0`` for strictest comparison.
    """
    target = _expand_path(golden_path)
    if not target.exists():
        raise FileNotFoundError(f"golden image not found: {target}")
    expected = Image.open(str(target))
    current = actual if actual is not None else _grab(region)
    differing, total, overlay = image_difference(
        current, expected,
        per_pixel_threshold=per_pixel_threshold, masks=masks,
    )
    diff_pct = (100.0 * differing / total) if total else 0.0
    matched = diff_pct <= max(0.0, float(tolerance))
    return DiffResult(
        matched=matched,
        diff_pct=diff_pct,
        differing_pixels=differing,
        total_pixels=total,
        tolerance_pct=float(tolerance),
        per_pixel_threshold=per_pixel_threshold,
        diff_image=overlay if not matched else None,
    )


__all__ = [
    "DiffResult", "MaskRegion",
    "compare_to_golden", "image_difference", "take_golden",
]
