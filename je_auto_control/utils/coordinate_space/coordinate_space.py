"""Map coordinates between a model's grid and physical screen pixels.

Computer-use / VLA models do not click in physical pixels: Anthropic recommends
downscaling the screenshot to XGA (~1024x768) and mapping clicks back; Gemini
computer-use returns a normalized **1000x1000** grid; others assume the declared
display size. A :class:`CoordinateSpace` captures the physical resolution and the
model's grid and converts both ways, so an agent loop can send the model a
right-sized screenshot and translate its clicks back to real coordinates.

Pure arithmetic for the mapping (no dependency); :func:`downscale_png` uses
Pillow, which is already a core dependency. Imports no ``PySide6``.
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CoordinateSpace:
    """A mapping between physical pixels and a model coordinate grid."""

    physical_w: int
    physical_h: int
    model_w: int
    model_h: int

    def to_physical(self, x: float, y: float) -> Tuple[int, int]:
        """Map a model-space ``(x, y)`` to physical pixels (clamped, rounded)."""
        px = round(x * self.physical_w / self.model_w)
        py = round(y * self.physical_h / self.model_h)
        return (_clamp(px, self.physical_w), _clamp(py, self.physical_h))

    def to_model(self, x: int, y: int) -> Tuple[int, int]:
        """Map physical pixels ``(x, y)`` to model space (clamped, rounded)."""
        mx = round(x * self.model_w / self.physical_w)
        my = round(y * self.model_h / self.physical_h)
        return (_clamp(mx, self.model_w), _clamp(my, self.model_h))

    @property
    def model_size(self) -> Tuple[int, int]:
        """The model grid as ``(width, height)``."""
        return (self.model_w, self.model_h)


def _clamp(value: int, size: int) -> int:
    return max(0, min(int(value), size - 1))


def xga_space(physical_w: int, physical_h: int, *, max_w: int = 1024,
              max_h: int = 768) -> CoordinateSpace:
    """Build a space that fits the screen within ``max_w`` x ``max_h``.

    The aspect ratio is preserved (the larger downscale factor wins), matching
    the Anthropic "downscale to XGA" recommendation.
    """
    scale = min(max_w / physical_w, max_h / physical_h, 1.0)
    model_w = max(1, round(physical_w * scale))
    model_h = max(1, round(physical_h * scale))
    return CoordinateSpace(physical_w, physical_h, model_w, model_h)


def normalized_space(physical_w: int, physical_h: int, *,
                     grid: int = 1000) -> CoordinateSpace:
    """Build a square normalized grid (default 1000x1000, Gemini-style)."""
    return CoordinateSpace(physical_w, physical_h, grid, grid)


def downscale_png(png: bytes, space: CoordinateSpace) -> bytes:
    """Resize a PNG screenshot to ``space``'s model size (for model input)."""
    import io

    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        resized = image.convert("RGB").resize(space.model_size)
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")
        return buffer.getvalue()
