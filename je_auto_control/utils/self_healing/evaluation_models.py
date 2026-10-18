"""Typed immutable inputs and measured results for fixed-frame locator evaluation."""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol

from je_auto_control.utils.exception.exceptions import AutoControlException

Point = tuple[float, float]
Box = tuple[float, float, float, float]
Method = Literal["image", "vlm", "miss"]


class HealingEvaluationError(AutoControlException, ValueError):
    """A comparison input, strategy result or dataset is invalid."""


def finite_numbers(values: object, length: int, label: str) -> tuple[float, ...]:
    """Validate a fixed-length finite numeric sequence without coercing strings/bools."""
    if not isinstance(values, (list, tuple)) or len(values) != length:
        raise HealingEvaluationError(f"{label} requires {length} finite numbers")
    if any(not _finite(value) for value in values):
        raise HealingEvaluationError(f"{label} requires {length} finite numbers")
    return tuple(float(value) for value in values)


def _finite(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def checked_box(value: object, label: str) -> Box:
    """Validate a positive-area half-open screen-space bounding box."""
    left, top, right, bottom = finite_numbers(value, 4, label)
    if right <= left or bottom <= top:
        raise HealingEvaluationError(f"{label} must have positive area")
    return left, top, right, bottom


def png_size(frame: bytes) -> tuple[int, int]:
    """Validate bounded PNG input without capturing a device or retaining a decoder."""
    if not isinstance(frame, bytes) or not frame or len(frame) > 16 * 1024 * 1024:
        raise HealingEvaluationError("frame must be immutable PNG bytes, at most 16 MiB")
    # pylint: disable-next=import-outside-toplevel  # reason: importing the facade does not initialize image decoders
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(frame)) as image:
            if image.format != "PNG" or image.width * image.height > 16_000_000:
                raise HealingEvaluationError("frame must be a PNG of at most 16 million pixels")
            image.verify()
            return image.size
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, SyntaxError) as error:
        raise HealingEvaluationError("cannot decode evaluation PNG") from error


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable dataset fields and explicit provenance
class EvaluationSample:
    """One PNG; origin/boxes are logical screen units, scale is pixels per unit.

    No box and expected_miss=False means unknown, not an expected miss.
    Regions must lie inside the supplied frame; every version sees this same input.
    """

    sample_id: str
    frame: bytes = field(repr=False)
    expected_box: Optional[Box] = None
    origin: Point = (0.0, 0.0)
    scale: float = 1.0
    expected_miss: bool = False
    region: Optional[Box] = None
    run_id: Optional[str] = None
    step_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id.strip():
            raise HealingEvaluationError("sample_id must be a nonempty string")
        width, height = png_size(self.frame)
        origin = finite_numbers(self.origin, 2, "origin")
        object.__setattr__(self, "origin", (origin[0], origin[1]))
        self._check_scale()
        self._check_labels()
        self._check_region(width, height)

    def _check_scale(self) -> None:
        if not _finite(self.scale) or self.scale <= 0:
            raise HealingEvaluationError("scale must be a positive finite number")
        if not isinstance(self.expected_miss, bool):
            raise HealingEvaluationError("expected_miss must be boolean")

    def _check_region(self, width: int, height: int) -> None:
        if self.region is not None:
            region = checked_box(self.region, "region")
            ox, oy = self.origin
            if region[0] < ox or region[1] < oy or region[2] > ox + width / self.scale \
                    or region[3] > oy + height / self.scale:
                raise HealingEvaluationError("region lies outside supplied frame")
            object.__setattr__(self, "region", region)

    def _check_labels(self) -> None:
        if self.expected_box is not None:
            if self.expected_miss:
                raise HealingEvaluationError("expected_box and expected_miss are mutually exclusive")
            object.__setattr__(self, "expected_box", checked_box(self.expected_box, "expected_box"))
        for value in (self.run_id, self.step_id):
            if value is not None and not isinstance(value, str):
                raise HealingEvaluationError("run_id/step_id must be strings or null")


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: serializable candidate metadata, not mutable services
class LocatorCandidate:
    """A point, not operation success; verification and optional USD cost are supplied separately."""

    coordinates: Optional[Point]
    method: Method
    fallback_used: bool = False
    verified: Optional[bool] = None
    backend: Optional[str] = None
    model: Optional[str] = None
    cost: Optional[float] = None
    timings_ms: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if self.method not in ("image", "vlm", "miss") or (self.method == "miss") != (self.coordinates is None):
            raise HealingEvaluationError("candidate method must agree with coordinates")
        if self.coordinates is not None:
            point = finite_numbers(self.coordinates, 2, "coordinates")
            object.__setattr__(self, "coordinates", (point[0], point[1]))
        self._check_metadata()
        self._check_timings()

    def _check_metadata(self) -> None:
        if not isinstance(self.fallback_used, bool) \
                or self.verified is not None and not isinstance(self.verified, bool):
            raise HealingEvaluationError("fallback_used/verified must be boolean (verified may be null)")
        if self.method == "vlm" and not self.fallback_used:
            raise HealingEvaluationError("a VLM candidate must record fallback_used")
        for value in (self.backend, self.model):
            if value is not None and not isinstance(value, str):
                raise HealingEvaluationError("backend/model must be strings or null")
        if self.cost is not None:
            _nonnegative(self.cost, "cost")

    def _check_timings(self) -> None:
        if not isinstance(self.timings_ms, (list, tuple)):
            raise HealingEvaluationError("timings_ms requires name/duration pairs")
        timings = tuple(self.timings_ms)
        for pair in timings:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise HealingEvaluationError("timings_ms requires name/duration pairs")
            name, duration = pair
            if not isinstance(name, str) or not name:
                raise HealingEvaluationError("timing names must be nonempty strings")
            _nonnegative(duration, "timing")
        if len({name for name, _ in timings}) != len(timings):
            raise HealingEvaluationError("timing names must be unique")
        object.__setattr__(self, "timings_ms", tuple((name, float(duration)) for name, duration in timings))


def _nonnegative(value: float, name: str) -> None:
    if not _finite(value) or value < 0:
        raise HealingEvaluationError(f"{name} must be a finite nonnegative number")


# pylint: disable-next=too-few-public-methods  # reason: one operation defines the supplied-frame strategy protocol
class LocatorStrategy(Protocol):
    """A strategy consumes supplied pixels; evaluation itself never captures or clicks."""

    def locate(self, sample: EvaluationSample) -> LocatorCandidate:
        """Locate against this exact frame and region, returning logical screen coordinates."""


@dataclass(frozen=True)
class EvaluationRatio:
    """Explicit numerator/denominator; no eligible samples gives a null value."""

    numerator: int
    denominator: int

    @property
    def value(self) -> Optional[float]:
        """The measured fraction, or unknown when denominator is zero."""
        return self.numerator / self.denominator if self.denominator else None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe ratio with its population visible."""
        return {"numerator": self.numerator, "denominator": self.denominator, "value": self.value}


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable case evidence including coordinates and provenance
class HealingAttempt:
    """One version/sample pair, with provenance but no image bytes."""

    sample_id: str
    version: str
    frame_hash: str
    candidate: LocatorCandidate
    correct: Optional[bool]
    false_positive: bool
    duration_ms: float
    run_id: Optional[str] = None
    step_id: Optional[str] = None
    expected_box: Optional[Box] = None
    expected_miss: bool = False
    origin: Point = (0.0, 0.0)
    scale: float = 1.0
    region: Optional[Box] = None


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: independent measured populations in one report value
class HealingVersionReport:
    """Counts and explicitly eligible populations for one locator version."""

    total: int
    unknown: int
    accuracy: EvaluationRatio
    false_positive: EvaluationRatio
    recovery: EvaluationRatio
    image_hit: EvaluationRatio
    fallback: EvaluationRatio
    miss: EvaluationRatio
    verification_unknown: int
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    cost_total: Optional[float]
    cost_known: int
