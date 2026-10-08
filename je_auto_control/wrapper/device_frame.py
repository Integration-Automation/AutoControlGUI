"""A captured device screen that knows how its pixels map to input coordinates.

A locator finds things in *pixels of the screenshot*; a tap is sent in the
device's *input coordinates*. The two differ on iOS, where WebDriverAgent
takes points and returns Retina pixels, and on any device whose screenshot
comes back in the panel's natural orientation while the display is rotated.
Tapping a located pixel as if it were a point lands in the wrong place, and
nothing reports it.

A :class:`DeviceFrame` carries the mapping with the image. Template matching,
OCR and the VLM locator search the frame — never the host's desktop — and
answer in device points, so the result can go straight into a gesture.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.wrapper.device_context import DeviceError

ORIENTATION_PORTRAIT = "portrait"
ORIENTATION_LANDSCAPE_LEFT = "landscape_left"
ORIENTATION_PORTRAIT_UPSIDE_DOWN = "portrait_upside_down"
ORIENTATION_LANDSCAPE_RIGHT = "landscape_right"
ORIENTATIONS = (ORIENTATION_PORTRAIT, ORIENTATION_LANDSCAPE_LEFT,
                ORIENTATION_PORTRAIT_UPSIDE_DOWN, ORIENTATION_LANDSCAPE_RIGHT)

#: TM_CCOEFF_NORMED is float32: an identical match scores just under 1.0.
_SCORE_EPSILON = 1e-5

Point = Tuple[int, int]


def _is_landscape(size: Tuple[int, int]) -> bool:
    return size[0] > size[1]


def upright_turn(image_size: Tuple[int, int], point_size: Tuple[int, int],
                 orientation: str) -> int:
    """Clockwise degrees a captured image must be turned to match the display.

    ``0`` when the image already has the display's shape. A landscape display
    with a portrait-shaped screenshot means the backend returned the panel's
    natural buffer; the orientation then says which way to turn it. An
    upside-down display cannot be told from the shape and is taken as already
    upright.
    """
    if _is_landscape(image_size) == _is_landscape(point_size) or image_size[0] == image_size[1]:
        return 0
    if orientation == ORIENTATION_LANDSCAPE_RIGHT:
        return 90
    return 270


@dataclass(frozen=True)
class DeviceFrame:
    """One screenshot of a device, upright, with its pixel-to-point mapping.

    ``image`` is a PIL image in the display's current orientation.
    ``point_size`` is the size of the input coordinate space in that same
    orientation: equal to the pixel size on Android, smaller by the Retina
    scale on iOS.
    """

    image: Any
    point_size: Tuple[int, int]
    orientation: str = ORIENTATION_PORTRAIT
    platform: str = ""
    device_id: str = ""

    def __post_init__(self) -> None:
        if min(self.point_size) <= 0 or min(self.pixel_size) <= 0:
            raise DeviceError(
                f"a device frame needs positive sizes, got pixels {self.pixel_size} "
                f"and points {self.point_size}")

    @classmethod
    def from_capture(cls, image: Any, point_size: Tuple[int, int], *,
                     orientation: str = ORIENTATION_PORTRAIT, platform: str = "",
                     device_id: str = "") -> "DeviceFrame":
        """Build a frame from a raw screenshot, turning it upright when needed."""
        size = (int(point_size[0]), int(point_size[1]))
        turn = upright_turn(image.size, size, orientation)
        if turn:
            # PIL turns counter-clockwise for positive angles.
            image = image.rotate(-turn, expand=True)
        return cls(image=image, point_size=size, orientation=orientation,
                   platform=platform, device_id=device_id)

    @property
    def pixel_size(self) -> Tuple[int, int]:
        """``(width, height)`` of the image in pixels."""
        return int(self.image.size[0]), int(self.image.size[1])

    @property
    def scale(self) -> float:
        """Pixels per input point along the width."""
        return self.pixel_size[0] / float(self.point_size[0])

    def pixel_to_point(self, x: float, y: float) -> Point:
        """The input coordinate under the centre of image pixel ``(x, y)``."""
        width, height = self.pixel_size
        if not (0 <= x < width and 0 <= y < height):
            raise DeviceError(f"pixel ({x}, {y}) is outside the {width}x{height} frame")
        return (int((x + 0.5) * self.point_size[0] / width),
                int((y + 0.5) * self.point_size[1] / height))

    def point_to_pixel(self, x: float, y: float) -> Point:
        """The image pixel under input coordinate ``(x, y)``."""
        width, height = self.pixel_size
        return (min(width - 1, max(0, int(x * width / self.point_size[0]))),
                min(height - 1, max(0, int(y * height / self.point_size[1]))))

    def png(self) -> bytes:
        """The frame as PNG bytes."""
        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        return buffer.getvalue()

    def save(self, file_path: Union[str, "os.PathLike[str]"]) -> str:
        """Write the frame as a PNG; returns the path."""
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(str(target), format="PNG")
        return str(target)

    def to_dict(self) -> Dict[str, Any]:
        """Geometry only (no pixels), for executor / MCP results."""
        return {"platform": self.platform, "device_id": self.device_id,
                "orientation": self.orientation,
                "pixel_size": list(self.pixel_size), "point_size": list(self.point_size),
                "scale": round(self.scale, 4)}

    # --- locating: every method searches this frame and answers in points ---

    def locate_image(self, template: Any, detect_threshold: float = 0.9) -> Point:
        """Centre of the best template match, in device points.

        Raises :class:`ImageNotFoundException` when nothing reaches the threshold.
        """
        threshold = float(detect_threshold)
        if not 0.0 <= threshold <= 1.0:
            raise ImageNotFoundException(
                f"detect_threshold must be between 0 and 1, got {detect_threshold!r}")
        from je_auto_control.utils.cv2_utils.optional import require_cv2
        cv2 = require_cv2()
        needle = _gray_template(cv2, template)
        haystack = _gray(cv2, self.image)
        if needle.shape[0] > haystack.shape[0] or needle.shape[1] > haystack.shape[1]:
            raise ImageNotFoundException("template is larger than the device frame")
        try:
            scores = cv2.matchTemplate(haystack, needle, cv2.TM_CCOEFF_NORMED)
        except cv2.error as error:
            raise ImageNotFoundException(f"cannot match template image: {error}") from error
        _low, best, _low_at, (left, top) = cv2.minMaxLoc(scores)
        if best < min(threshold, 1.0 - _SCORE_EPSILON):
            raise ImageNotFoundException(
                f"template not found in the device frame (best score {best:.3f})")
        return self.pixel_to_point(left + needle.shape[1] // 2, top + needle.shape[0] // 2)

    def locate_text(self, target: str, *, lang: str = "eng", min_confidence: float = 60.0,
                    case_sensitive: bool = False, backend: Any = None) -> Optional[Point]:
        """Centre of the first OCR match for ``target``, in device points, or ``None``."""
        from je_auto_control.utils.ocr.backends import get_backend
        from je_auto_control.utils.ocr.text_span import find_spans
        engine = get_backend(backend) if backend is None or isinstance(backend, str) else backend
        matches = engine.image_to_matches(self.image, lang, float(min_confidence))
        spans = find_spans(matches, target, case_sensitive=case_sensitive)
        if not spans:
            return None
        span = spans[0]
        left = min(box.x for box in span)
        top = min(box.y for box in span)
        right = max(box.x + box.width for box in span)
        bottom = max(box.y + box.height for box in span)
        return self.pixel_to_point((left + right) // 2, (top + bottom) // 2)

    def locate_description(self, description: str, *, model: Optional[str] = None,
                           backend: Any = None) -> Optional[Point]:
        """Where a vision-language model says ``description`` is, in device points."""
        if not description or not description.strip():
            raise ValueError("description must be a non-empty string")
        from je_auto_control.utils.vision.backends import get_backend
        from je_auto_control.utils.vision.backends.base import VLMNotAvailableError
        bound = backend if backend is not None else get_backend()
        if not bound.available:
            raise VLMNotAvailableError(
                "no VLM backend configured; set ANTHROPIC_API_KEY or "
                "OPENAI_API_KEY and install the matching SDK")
        reply = bound.locate(self.png(), description, model=model)
        if reply is None:
            return None
        width, height = self.pixel_size
        if not (0 <= reply[0] < width and 0 <= reply[1] < height):
            # Off the image the model was shown: a misread, not a location.
            return None
        return self.pixel_to_point(reply[0], reply[1])


def _gray(cv2: Any, image: Any) -> Any:
    """``image`` (PIL image or array) as a 2-D ``uint8`` grayscale array."""
    import numpy as np
    array = np.asarray(image)
    if array.ndim == 3 and array.shape[2] == 4:
        array = array[:, :, :3]
    if array.ndim == 3:
        array = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    if array.ndim != 2:
        raise ImageNotFoundException(f"cannot search an image of shape {array.shape}")
    return array.astype(np.uint8, copy=False)


def _gray_template(cv2: Any, template: Any) -> Any:
    """Load ``template`` (path, PIL image or array) as a grayscale array."""
    try:
        if isinstance(template, (str, os.PathLike)):
            if not os.path.isfile(template):
                raise ImageNotFoundException(f"template image not found: {template}")
            from je_auto_control.utils.cv2_utils.image_file import read_image
            return read_image(os.fspath(template), cv2.IMREAD_GRAYSCALE)
        return _gray(cv2, template)
    except (ValueError, TypeError, cv2.error) as error:
        raise ImageNotFoundException(f"cannot read template image: {template!r}") from error


__all__ = [
    "DeviceFrame", "ORIENTATIONS", "ORIENTATION_LANDSCAPE_LEFT",
    "ORIENTATION_LANDSCAPE_RIGHT", "ORIENTATION_PORTRAIT",
    "ORIENTATION_PORTRAIT_UPSIDE_DOWN", "upright_turn",
]
