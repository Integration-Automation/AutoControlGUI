"""Image and explicitly supplied VLM strategies over provided PNGs, without screen capture."""
from __future__ import annotations

import io
from dataclasses import dataclass, replace
from math import ceil, floor
from time import perf_counter
from typing import Any, Optional

from je_auto_control.utils.cv2_utils.optional import require_cv2
from je_auto_control.utils.cv2_utils.template_detection import _to_gray
from je_auto_control.utils.self_healing.evaluation_models import (
    EvaluationSample, HealingEvaluationError, LocatorCandidate, LocatorStrategy, Point, finite_numbers, png_size,
)
from je_auto_control.utils.vision.backends.base import VLMBackend, VLMNotAvailableError


@dataclass(frozen=True)
class _FrameView:
    png: bytes
    origin: Point
    scale: float
    size: tuple[int, int]

    def screen_point(self, point: Point) -> Point:
        """Validate local pixels and floor the transformed logical pointer coordinate."""
        x, y = finite_numbers(point, 2, "backend coordinates")
        if not 0 <= x < self.size[0] or not 0 <= y < self.size[1]:
            raise HealingEvaluationError("locator returned a point outside supplied search pixels")
        return floor(self.origin[0] + x / self.scale), floor(self.origin[1] + y / self.scale)


def _view(sample: EvaluationSample) -> _FrameView:
    size = png_size(sample.frame)
    if sample.region is None:
        return _FrameView(sample.frame, sample.origin, sample.scale, size)
    left, top, right, bottom = sample.region
    ox, oy = sample.origin
    bounds = (ceil((left - ox) * sample.scale), ceil((top - oy) * sample.scale),
              floor((right - ox) * sample.scale), floor((bottom - oy) * sample.scale))
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise HealingEvaluationError("region contains no complete pixels")
    # pylint: disable-next=import-outside-toplevel  # reason: initialize optional decoders only when supplied pixels are used
    from PIL import Image
    stream = io.BytesIO()
    with Image.open(io.BytesIO(sample.frame)) as image:
        with image.crop(bounds) as cropped:
            cropped.save(stream, format="PNG")
    origin = ox + bounds[0] / sample.scale, oy + bounds[1] / sample.scale
    return _FrameView(stream.getvalue(), origin, sample.scale,
                      (bounds[2] - bounds[0], bounds[3] - bounds[1]))


def _gray(png: bytes) -> Any:
    # pylint: disable-next=import-outside-toplevel  # reason: keep decoder work out of facade initialization
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        # Own the array rather than referencing a decoder closed on return.
        return _to_gray(require_cv2(), image).copy()


@dataclass(frozen=True)
class TemplateFrameLocator:
    """Normalized template matching; an optional fallback gets the identical sample.

    Template pixels are supplied explicitly. Constant templates are refused because
    normalized correlation is undefined and can otherwise match every location.
    Thresholds use the runtime matcher's float32 epsilon at 1.0.
    """

    template: bytes
    threshold: float = 0.9
    fallback: Optional[LocatorStrategy] = None

    def __post_init__(self) -> None:
        png_size(self.template)
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)) \
                or not 0 <= self.threshold <= 1:
            raise HealingEvaluationError("threshold must be a number between 0 and 1")

    def locate(self, sample: EvaluationSample) -> LocatorCandidate:
        """Match only supplied search pixels, then optionally run the explicit fallback."""
        started = perf_counter()
        point = self._match(_view(sample))
        elapsed = (perf_counter() - started) * 1000
        if point is not None:
            return LocatorCandidate(point, "image", timings_ms=(("image", elapsed),))
        if self.fallback is None:
            return LocatorCandidate(None, "miss", timings_ms=(("image", elapsed),))
        result = self.fallback.locate(sample)
        timings = (("image", elapsed), *((f"fallback.{name}", value) for name, value in result.timings_ms))
        return replace(result, fallback_used=True, timings_ms=timings)

    def _match(self, view: _FrameView) -> Optional[Point]:
        cv2 = require_cv2()
        frame, template = _gray(view.png), _gray(self.template)
        if float(template.std()) == 0:
            raise HealingEvaluationError("constant template cannot use normalized correlation")
        height, width = template.shape[:2]
        if height > frame.shape[0] or width > frame.shape[1]:
            return None
        # pylint: disable-next=no-member  # reason: optional OpenCV exports these C extension symbols at runtime
        scores = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        # pylint: disable-next=no-member  # reason: optional OpenCV exports this C extension symbol at runtime
        _low, score, _low_at, (x, y) = cv2.minMaxLoc(scores)
        if score < min(self.threshold, 1.0 - 1e-5):
            return None
        return view.screen_point((x + width // 2, y + height // 2))


@dataclass(frozen=True)
class VLMFrameLocator:
    """Call an explicitly provided backend on supplied PNG bytes; never choose a paid backend implicitly.

    Backend replies use local image pixels. Origin and pixels-per-logical-unit scale
    are applied once. A point from a model does not imply post-operation verification.
    """

    backend: VLMBackend
    description: str
    model: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.description, str) or not self.description.strip():
            raise HealingEvaluationError("description must be nonempty")
        if not isinstance(self.backend, VLMBackend):
            raise HealingEvaluationError("backend must implement VLMBackend")
        if self.model is not None and not isinstance(self.model, str):
            raise HealingEvaluationError("model must be a string or null")

    def locate(self, sample: EvaluationSample) -> LocatorCandidate:
        """Use the same cropped pixels as the image strategy, without capture or verification."""
        if not self.backend.available:
            raise VLMNotAvailableError("explicit evaluation backend is unavailable")
        started = perf_counter()
        view = _view(sample)
        point = self.backend.locate(view.png, self.description, model=self.model)
        coordinates = None if point is None else view.screen_point(point)
        elapsed = (perf_counter() - started) * 1000
        return LocatorCandidate(coordinates, "vlm" if point is not None else "miss", fallback_used=True,
                                backend=self.backend.name, model=self.model, timings_ms=(("vlm", elapsed),))
