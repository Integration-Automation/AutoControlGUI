"""Bounded NumPy/Pillow image matching and conversion when OpenCV is unavailable.

Supports the small operation set used by screenshots, template detection and
fixed-frame healing. It is not a general replacement for OpenCV or video codecs.
Correlation is tiled to bound FFT scratch space independently of desktop size.
"""
from __future__ import annotations

import io
from sys import float_info
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw, UnidentifiedImageError

from je_auto_control.utils.cv2_utils.optional import ImageBackendError

# pylint: disable-next=invalid-name  # reason: the backend seam preserves OpenCV's error attribute
error = ImageBackendError
IMREAD_GRAYSCALE = 0
IMREAD_COLOR = 1
COLOR_RGB2BGR = 4
COLOR_RGB2GRAY = 7
TM_CCOEFF_NORMED = 5
MAX_FRAME_PIXELS = 16_777_216
MAX_FFT_PIXELS = 4_194_304
_TILE_SIDE = 512
BACKEND_NAME = "numpy-pillow"


def _array(image: Any) -> Any:
    value = np.asarray(image)
    if value.ndim not in (2, 3) or not value.size or value.shape[0] * value.shape[1] > MAX_FRAME_PIXELS:
        raise error("image exceeds the fallback frame budget or has invalid dimensions")
    if value.dtype not in (np.uint8, np.float32):
        raise error("fallback images must be uint8 or float32")
    if not np.isfinite(value).all():
        raise error("fallback image contains non-finite pixels")
    return value


# pylint: disable-next=invalid-name  # reason: this compatibility method implements the existing OpenCV seam
def cvtColor(image: Any, code: int) -> Any:
    """Convert RGB/RGBA to gray or BGR while preserving the screenshot contract."""
    value = _array(image)
    if value.ndim != 3 or value.shape[2] not in (3, 4):
        raise error("RGB conversion requires three or four channels")
    if code == COLOR_RGB2BGR:
        return value[:, :, 2::-1].copy()
    if code != COLOR_RGB2GRAY:
        raise error("unsupported fallback color conversion")
    if value.dtype == np.float32:
        return value[:, :, 0] * 0.299 + value[:, :, 1] * 0.587 + value[:, :, 2] * 0.114
    # BT.601 15-bit coefficients: OpenCV color.simd_helpers.hpp / RGB2Gray<uchar>.
    rgb = value[:, :, :3].astype(np.uint32)
    return ((rgb[:, :, 0] * 9798 + rgb[:, :, 1] * 19235 + rgb[:, :, 2] * 3735 + 16384) >> 15).astype(np.uint8)


def _window_sums(value: Any, shape: tuple[int, int]) -> Any:
    integral = np.pad(value.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    height, width = shape
    return (integral[height:, width:] - integral[:-height, width:]
            - integral[height:, :-width] + integral[:-height, :-width])


def _fft_shape(value: Any, template: Any) -> tuple[int, int]:
    dimensions = tuple(1 << (a + b - 2).bit_length() for a, b in zip(value.shape, template.shape))
    if dimensions[0] * dimensions[1] > MAX_FFT_PIXELS:
        raise error("template exceeds the fallback FFT budget; use a smaller template or OpenCV")
    return int(dimensions[0]), int(dimensions[1])


def _score_tile(value: Any, centered: Any, energy: float, kernel_cache: dict[tuple[int, int], Any]) -> Any:
    value = value.astype(np.float64)
    shape = _fft_shape(value, centered)
    if shape not in kernel_cache:
        kernel_cache.clear()
        kernel_cache[shape] = np.fft.rfft2(centered[::-1, ::-1], s=shape, axes=(0, 1))
    convolution = np.fft.irfft2(np.fft.rfft2(value, s=shape, axes=(0, 1)) * kernel_cache[shape], s=shape, axes=(0, 1))
    height, width = centered.shape
    numerator = convolution[height - 1:value.shape[0], width - 1:value.shape[1]]
    total = _window_sums(value, centered.shape)
    squares = _window_sums(value * value, centered.shape)
    variance = np.maximum(squares - total * total / centered.size, 0)
    denominator = np.sqrt(variance * energy)
    scores = np.zeros(numerator.shape, dtype=np.float64)
    np.divide(numerator, denominator, out=scores, where=denominator > 1e-12)
    return np.clip(scores, -1, 1).astype(np.float32)


# pylint: disable-next=invalid-name  # reason: this compatibility method implements the existing OpenCV seam
def matchTemplate(image: Any, template: Any, method: int) -> Any:
    """Compute gray TM_CCOEFF_NORMED scores with bounded tiled FFT correlation."""
    if method != TM_CCOEFF_NORMED:
        raise error("fallback supports only normalized coefficient template matching")
    frame, target = _array(image), _array(template)
    if frame.ndim != 2 or target.ndim != 2 or frame.dtype != target.dtype:
        raise error("fallback matching requires two grayscale images of the same dtype")
    height, width = target.shape
    if height > frame.shape[0] or width > frame.shape[1]:
        raise error("template is larger than the searched image")
    output_shape = (frame.shape[0] - height + 1, frame.shape[1] - width + 1)
    centered = target.astype(np.float64) - target.mean(dtype=np.float64)
    energy = float(np.sum(centered * centered))
    if energy < float_info.epsilon:
        return np.ones(output_shape, dtype=np.float32)
    return _matching_tiles(frame, centered, energy, output_shape)


def _matching_tiles(frame: Any, centered: Any, energy: float, output_shape: tuple[int, int]) -> Any:
    """Reuse one bounded kernel while producing every tile of the score map."""
    height, width = centered.shape
    result = np.empty(output_shape, dtype=np.float32)
    # Cache one kernel only: edge tiles can have different FFT shapes.
    kernel_cache: dict[tuple[int, int], Any] = {}
    for top in range(0, output_shape[0], _TILE_SIDE):
        for left in range(0, output_shape[1], _TILE_SIDE):
            rows = min(_TILE_SIDE, output_shape[0] - top)
            cols = min(_TILE_SIDE, output_shape[1] - left)
            tile = frame[top:top + rows + height - 1, left:left + cols + width - 1]
            result[top:top + rows, left:left + cols] = _score_tile(tile, centered, energy, kernel_cache)
    return result


# pylint: disable-next=invalid-name  # reason: this compatibility method implements the existing OpenCV seam
def minMaxLoc(scores: Any) -> tuple[float, float, tuple[int, int], tuple[int, int]]:
    """Return extrema and first row-major positions, matching template detection."""
    value = np.asarray(scores)
    if value.ndim != 2 or not value.size or not np.isfinite(value).all():
        raise error("score map must be a nonempty finite plane")
    minimum, maximum = int(np.argmin(value)), int(np.argmax(value))
    min_y, min_x = divmod(minimum, value.shape[1])
    max_y, max_x = divmod(maximum, value.shape[1])
    return float(value.flat[minimum]), float(value.flat[maximum]), (min_x, min_y), (max_x, max_y)


def imdecode(buffer: Any, flags: int) -> Any:
    """Decode bytes through Pillow with explicit RGB/gray conversion."""
    if flags not in (IMREAD_GRAYSCALE, IMREAD_COLOR):
        raise error("unsupported fallback decode flags")
    try:
        with Image.open(io.BytesIO(bytes(buffer))) as image:
            if image.width * image.height > MAX_FRAME_PIXELS:
                raise error("decoded image exceeds the fallback frame budget")
            if image.mode in ("I", "F", "I;16", "I;16L", "I;16B"):
                raise error("fallback decoding requires an 8-bit image")
            rgb = np.asarray(image.convert("RGB"))
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as failure:
        raise error("cannot decode image") from failure
    return cvtColor(rgb, COLOR_RGB2GRAY if flags == IMREAD_GRAYSCALE else COLOR_RGB2BGR)


def imencode(extension: str, image: Any) -> tuple[bool, Any]:
    """Encode uint8 gray/BGR images in supported Pillow file formats."""
    formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".bmp": "BMP",
               ".tif": "TIFF", ".tiff": "TIFF", ".webp": "WEBP"}
    format_name = formats.get(extension.lower())
    value = _array(image)
    if format_name is None or value.dtype != np.uint8:
        raise error("unsupported fallback image format or dtype")
    if value.ndim == 3:
        if value.shape[2] != 3:
            raise error("fallback encoding expects gray or BGR")
        value = value[:, :, ::-1]
    output = io.BytesIO()
    try:
        Image.fromarray(value).save(output, format=format_name)
    except (OSError, ValueError) as failure:
        raise error("cannot encode image") from failure
    return True, np.frombuffer(output.getvalue(), dtype=np.uint8)


def rectangle(image: Any, first: tuple[int, int], last: tuple[int, int],
              color: Sequence[int], thickness: int) -> Any:
    """Draw an in-place border for template previews without changing frame shape."""
    value = _array(image)
    if value.dtype != np.uint8:
        raise error("fallback drawing requires uint8")
    if not value.flags.writeable:
        raise error("fallback drawing requires a writable frame copy")
    canvas = Image.fromarray(value)
    fill = int(color[0]) if value.ndim == 2 else tuple(color)
    ImageDraw.Draw(canvas).rectangle((*first, *last), outline=fill, width=max(1, thickness))
    np.copyto(value, np.asarray(canvas))
    return image
