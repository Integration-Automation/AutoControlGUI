"""Immutable device PNG evidence with native-point mapping and fixed-frame search."""
from __future__ import annotations

from dataclasses import dataclass, field
import io
import math
from typing import Any, TYPE_CHECKING, Optional

from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper.mobile_gesture import Point, finite_point

if TYPE_CHECKING:
    from je_auto_control.utils.ocr.backends.base import OCRBackend
    from je_auto_control.utils.ocr.ocr_engine import TextMatch
    from je_auto_control.utils.self_healing.evaluation_models import LocatorPrediction, LocatorStrategy


@dataclass(frozen=True)
class DeviceFrame:
    """One PNG in its observed device orientation, without any desktop capture.

    point_size is the native input viewport (UIKit points or Android pixels).
    orientation is clockwise degrees from natural orientation. rotation records
    additional display-only clockwise rotation; native coordinates stay fixed.
    A frame is a snapshot, so reject/recapture after the device rotates.
    """

    png: bytes = field(repr=False)
    context: DeviceContext
    point_size: Point
    orientation: int = 0
    rotation: int = 0
    pixel_size: tuple[int, int] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.context, DeviceContext):
            raise DeviceSessionError('frame must carry a frozen device context')
        size = finite_point(self.point_size)
        if min(size) <= 0 or not all(_valid_angle(angle) for angle in (self.orientation, self.rotation)):
            raise DeviceSessionError('frame viewport and orientation must be valid')
        if not isinstance(self.png, bytes) or not self.png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise DeviceSessionError('device frame must contain immutable PNG bytes')
        try:
            with self.image() as image:
                object.__setattr__(self, 'pixel_size', image.size)
                image.verify()
        except (OSError, ValueError) as failure:
            raise DeviceSessionError('device frame PNG is invalid') from failure
        object.__setattr__(self, 'point_size', size)
        width, height = self.pixel_size if self.rotation % 180 == 0 else self.pixel_size[::-1]
        if abs(width * size[1] - height * size[0]) > max(size):
            raise DeviceSessionError('frame aspect ratio does not match native viewport; recapture after rotation')

    def image(self) -> Any:
        """Decode supplied bytes; caller closes the returned Pillow image."""
        # pylint: disable-next=import-outside-toplevel  # reason: optional imaging remains lazy
        from PIL import Image
        return Image.open(io.BytesIO(self.png))

    def pixel_to_point(self, pixel: Point) -> Point:
        """Undo display rotation then scale into the observed native viewport."""
        x, y = finite_point(pixel)
        width, height = self.pixel_size
        if x >= width or y >= height:
            raise DeviceSessionError('frame pixel is outside the captured image')
        transforms = {
            0: (x / width, y / height),
            90: (y / height, (width - 1 - x) / width),
            180: ((width - 1 - x) / width, (height - 1 - y) / height),
            270: ((height - 1 - y) / height, x / width),
        }
        nx, ny = transforms[self.rotation]
        return nx * self.point_size[0], ny * self.point_size[1]

    def rotated(self, degrees: int) -> DeviceFrame:
        """Return another immutable view, preserving native input mapping."""
        if isinstance(degrees, bool) or degrees not in (0, 90, 180, 270):
            raise DeviceSessionError('display rotation must be 0, 90, 180 or 270 degrees')
        with self.image() as image, image.rotate(-degrees, expand=True) as rotated:
            output = io.BytesIO()
            rotated.save(output, format='PNG')
        return DeviceFrame(output.getvalue(), self.context, self.point_size,
                           self.orientation, (self.rotation + degrees) % 360)

    def locate(self, strategy: LocatorStrategy) -> LocatorPrediction:
        """Use a template/VLM strategy on these bytes; result stays in frame pixels."""
        # pylint: disable-next=import-outside-toplevel  # reason: evaluation is optional until requested
        from je_auto_control.utils.self_healing.evaluation_models import EvaluationSample
        return strategy.locate(EvaluationSample(self.png, context={'device_id': self.context.device_id}))

    def ocr(self, *, backend: Optional[OCRBackend] = None, lang: str = 'eng',
            min_confidence: float = 60) -> list[TextMatch]:
        """Extract image-local OCR matches from this same immutable frame."""
        # pylint: disable-next=import-outside-toplevel  # reason: OCR engines remain lazy
        from je_auto_control.utils.ocr.backends import get_backend
        if not isinstance(lang, str) or not lang.strip() or not _valid_confidence(min_confidence):
            raise DeviceSessionError('OCR language/confidence must be valid')
        engine = backend if backend is not None else get_backend()
        with self.image() as image, image.convert('RGB') as rgb:
            return engine.image_to_matches(rgb, lang, min_confidence)


def _valid_angle(value: int) -> bool:
    return not isinstance(value, bool) and value in (0, 90, 180, 270)


def _valid_confidence(value: float) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 <= value <= 100)
