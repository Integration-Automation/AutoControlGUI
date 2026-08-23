"""Average + dominant colour of an image (or sub-region).

Goes beyond single-pixel ``get_pixel``: answer "is this region mostly
red?", detect a theme, or assert a colour without an exact template.
Dominant colour is found by quantising colour space into buckets, taking
the busiest bucket, then averaging the real pixels in it for an accurate
representative. Pure Pillow — no Qt, no screen capture — so it is fully
unit-testable.
"""
from __future__ import annotations

import io
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union,
)

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from PIL import Image

ImageSource = Union[str, Path, bytes, "Image.Image"]
RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class ColorStats:
    """Colour summary of an image region."""

    average_rgb: RGB
    dominant_rgb: RGB
    dominant_fraction: float
    pixel_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_rgb(source: ImageSource) -> "Image.Image":
    from PIL import Image
    if isinstance(source, Image.Image):
        return source.convert("RGB")
    if isinstance(source, bytes):
        return Image.open(io.BytesIO(source)).convert("RGB")
    return Image.open(str(source)).convert("RGB")


def _average_color(pixels: List[RGB], count: int) -> RGB:
    return (sum(p[0] for p in pixels) // count,
            sum(p[1] for p in pixels) // count,
            sum(p[2] for p in pixels) // count)


def _dominant_color(pixels: List[RGB], count: int, buckets: int
                    ) -> Tuple[RGB, float]:
    step = max(1, 256 // max(1, int(buckets)))

    def _bucket(pixel: RGB) -> RGB:
        return (pixel[0] // step, pixel[1] // step, pixel[2] // step)

    counter = Counter(_bucket(pixel) for pixel in pixels)
    top, top_count = counter.most_common(1)[0]
    members = [pixel for pixel in pixels if _bucket(pixel) == top]
    member_count = len(members) or 1
    dominant = _average_color(members, member_count)
    return dominant, round(top_count / count, 4)


def region_color_stats(source: ImageSource,
                       region: Optional[Sequence[int]] = None,
                       buckets: int = 8) -> ColorStats:
    """Return the average + dominant colour of ``source`` (or a sub-region).

    ``region`` is ``[x1, y1, x2, y2]``. The image is downsampled before
    analysis (colour stats don't need full resolution), so this stays fast
    even on a full-screen capture.
    """
    image = _load_rgb(source)
    if region is not None:
        left, top, right, bottom = (int(v) for v in region)
        image = image.crop((left, top, right, bottom))
    image.thumbnail((128, 128))
    pixels: List[RGB] = list(image.getdata())
    count = len(pixels)
    if count == 0:
        return ColorStats((0, 0, 0), (0, 0, 0), 0.0, 0)
    average = _average_color(pixels, count)
    dominant, fraction = _dominant_color(pixels, count, buckets)
    return ColorStats(average, dominant, fraction, count)
