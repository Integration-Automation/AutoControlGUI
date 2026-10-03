"""Immutable fixed-frame inputs, predictions and labelled comparison reports."""
from __future__ import annotations

import hashlib
import math
from abc import abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Optional, Protocol, Tuple

from je_auto_control.utils.action_journal.events import JSONValue
from je_auto_control.utils.exception.exceptions import AutoControlException

Point = Tuple[float, float]
Box = Tuple[float, float, float, float]


class HealingEvaluationError(AutoControlException, ValueError):
    """An evaluation input or candidate revision violates its contract."""


def _vector(value: Tuple[float, ...], length: int, *, positive: bool = False) -> None:
    if len(value) != length:
        raise HealingEvaluationError('geometry has the wrong number of coordinates')
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
           or (positive and item <= 0) for item in value):
        raise HealingEvaluationError('geometry must be finite with positive dimensions/scales')


@dataclass(frozen=True)
class EvaluationSample:  # pylint: disable=too-many-instance-attributes  # reason: immutable labelled frame metadata
    """Immutable frame bytes; expected boxes use logical desktop xywh coordinates.

    Strategies return frame pixels. Origin is the frame's actual desktop origin;
    scale is pixels per logical unit. An absent box is unknown unless expected_miss
    explicitly labels a negative. Operation verification is a separate annotation.
    """
    frame: bytes
    expected_box: Optional[Box] = None
    origin: Point = (0, 0)
    scale: Point = (1, 1)
    expected_miss: bool = False
    sample_id: str = ''
    operation_verified: Optional[bool] = None
    context: Optional[Mapping[str, str]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.frame, bytes) or not self.frame:
            raise HealingEvaluationError('frame must be nonempty immutable bytes')
        _vector(self.origin, 2)
        _vector(self.scale, 2, positive=True)
        object.__setattr__(self, 'origin', tuple(self.origin))
        object.__setattr__(self, 'scale', tuple(self.scale))
        if self.expected_box is not None:
            _vector(self.expected_box, 4)
            if min(self.expected_box[2:]) <= 0 or self.expected_miss:
                raise HealingEvaluationError('expected box dimensions must be positive and not expected_miss')
            object.__setattr__(self, 'expected_box', tuple(self.expected_box))
        if not isinstance(self.sample_id, str) or not isinstance(self.expected_miss, bool):
            raise HealingEvaluationError('sample identity and expected_miss have invalid types')
        if self.operation_verified is not None and not isinstance(self.operation_verified, bool):
            raise HealingEvaluationError('operation_verified must be a boolean or unknown')
        self._freeze_context()

    def _freeze_context(self) -> None:
        if self.context is not None:
            if any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.context.items()):
                raise HealingEvaluationError('sample context must contain text identities and source paths')
            object.__setattr__(self, 'context', MappingProxyType(dict(self.context)))

    @property
    def frame_hash(self) -> str:
        """Content identity shared by every compared strategy."""
        return hashlib.sha256(self.frame).hexdigest()


@dataclass(frozen=True)
class LocatorPrediction:
    """A frame-pixel location, with strategy identity and optional measured cost."""
    coordinates: Optional[Point]
    method: str = 'image'
    backend: Optional[str] = None
    model: Optional[str] = None
    cost: Optional[float] = None

    def __post_init__(self) -> None:
        if self.coordinates is not None:
            _vector(self.coordinates, 2)
        if self.method not in {'image', 'vlm', 'miss'}:
            raise HealingEvaluationError('unsupported prediction method')
        if self.cost is not None and (not math.isfinite(self.cost) or self.cost < 0):
            raise HealingEvaluationError('cost must be finite and nonnegative')


class LocatorStrategy(Protocol):  # pylint: disable=too-few-public-methods  # reason: one typed strategy operation
    """A locator that consumes supplied bytes without taking another screenshot."""

    @abstractmethod
    def locate(self, sample: EvaluationSample) -> LocatorPrediction:
        """Return a prediction in frame pixels for this immutable sample."""
        raise NotImplementedError


@dataclass(frozen=True)
class Ratio:
    """An explicit numerator/denominator; empty populations remain unknown."""
    numerator: int
    denominator: int

    @property
    def value(self) -> Optional[float]:
        """The ratio, or None when no eligible annotations exist."""
        return self.numerator / self.denominator if self.denominator else None

    def to_dict(self) -> Dict[str, JSONValue]:
        """Wire representation retaining both counts."""
        return {'numerator': self.numerator, 'denominator': self.denominator, 'value': self.value}


@dataclass(frozen=True)
class EvaluationTrial:  # pylint: disable=too-many-instance-attributes  # reason: frozen report row keeps independent evidence
    """One version's detection and independently annotated operation outcome."""
    sample_id: str
    frame_hash: str
    coordinates: Optional[Point]
    method: str
    duration_ms: float
    correct: Optional[bool]
    expected_present: Optional[bool]
    error: Optional[str] = None
    operation_verified: Optional[bool] = None
    backend: Optional[str] = None
    model: Optional[str] = None
    cost: Optional[float] = None
    sample: Optional[Dict[str, JSONValue]] = None

    def to_dict(self) -> Dict[str, JSONValue]:
        """Safe report fields; image bytes and arbitrary strategy objects are excluded."""
        return {'sample_id': self.sample_id, 'frame_hash': self.frame_hash,
                'coordinates': list(self.coordinates) if self.coordinates is not None else None,
                'method': self.method, 'duration_ms': self.duration_ms, 'correct': self.correct,
                'expected_present': self.expected_present, 'error': self.error,
                'operation_verified': self.operation_verified, 'backend': self.backend,
                'model': self.model, 'cost': self.cost, 'sample': self.sample}


def _percentile(values: Tuple[float, ...], quantile: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


@dataclass(frozen=True)
class VersionReport:  # pylint: disable=too-many-public-methods  # reason: explicit derived metrics share one immutable trial set
    """Counts and rates over one version; unknown labels never add successes."""
    version: str
    trials: Tuple[EvaluationTrial, ...]

    @property
    def unknown(self) -> int:
        """Trials without a positive or negative ground-truth annotation."""
        return sum(trial.correct is None for trial in self.trials)

    @property
    def correct(self) -> int:
        """Correct labelled hits or labelled negative misses."""
        return sum(trial.correct is True for trial in self.trials)

    @property
    def false_positive(self) -> int:
        """Wrong labelled predictions, including guesses on expected negatives."""
        return sum(trial.correct is False and trial.coordinates is not None and trial.error is None
                   for trial in self.trials)

    @property
    def miss(self) -> int:
        """Trials with no returned coordinates, including separately reported errors."""
        return sum(trial.coordinates is None for trial in self.trials)

    @property
    def errors(self) -> int:
        """Strategy failures; these never count as a correct negative miss."""
        return sum(trial.error is not None for trial in self.trials)

    @property
    def image_hit(self) -> int:
        """Image detections, independent of their labelled correctness."""
        return sum(trial.method == 'image' and trial.coordinates is not None for trial in self.trials)

    @property
    def fallback(self) -> int:
        """Trials that reached the VLM strategy, including failed recovery."""
        return sum(trial.method == 'vlm' for trial in self.trials)

    @property
    def accuracy(self) -> Ratio:
        """Detection correctness over all labelled trials."""
        return Ratio(self.correct, len(self.trials) - self.unknown)

    @property
    def recovery(self) -> Ratio:
        """Correct fallback detections over labelled positive fallback attempts."""
        eligible = [trial for trial in self.trials if trial.method == 'vlm' and trial.expected_present is True]
        return Ratio(sum(trial.correct is True for trial in eligible), len(eligible))

    @property
    def false_positive_rate(self) -> Ratio:
        """Wrong labelled guesses over all labelled trials returning coordinates."""
        denominator = sum(trial.correct is not None and trial.coordinates is not None for trial in self.trials)
        return Ratio(self.false_positive, denominator)

    @property
    def operation_success(self) -> Ratio:
        """Independent post-operation annotations; detection alone contributes nothing."""
        verified = [trial.operation_verified for trial in self.trials if trial.operation_verified is not None]
        return Ratio(sum(value is True for value in verified), len(verified))

    @property
    def p50_ms(self) -> Optional[float]:
        """Interpolated median latency over all attempts."""
        return _percentile(tuple(trial.duration_ms for trial in self.trials), 0.5)

    @property
    def p95_ms(self) -> Optional[float]:
        """Interpolated 95th-percentile latency over all attempts."""
        return _percentile(tuple(trial.duration_ms for trial in self.trials), 0.95)

    def to_dict(self) -> Dict[str, JSONValue]:
        """JSON report with count denominators, trial provenance and available cost."""
        costs = [trial.cost for trial in self.trials if trial.cost is not None]
        return {'version': self.version, 'total': len(self.trials), 'unknown': self.unknown,
                'correct': self.correct, 'false_positive': self.false_positive, 'miss': self.miss,
                'errors': self.errors, 'image_hit': self.image_hit, 'fallback': self.fallback,
                'accuracy': self.accuracy.to_dict(), 'recovery': self.recovery.to_dict(),
                'false_positive_rate': self.false_positive_rate.to_dict(),
                'operation_success': self.operation_success.to_dict(), 'p50_ms': self.p50_ms,
                'p95_ms': self.p95_ms, 'cost_total': sum(costs) if costs else None,
                'cost_samples': len(costs), 'trials': [trial.to_dict() for trial in self.trials]}


@dataclass(frozen=True)
class HealingComparison:
    """Comparable per-version reports sharing immutable frame identities."""
    sample_count: int
    versions: Mapping[str, VersionReport]

    def to_dict(self) -> Dict[str, JSONValue]:
        """Export a schema-versioned comparison without performing any actions."""
        return {'schema_version': 1, 'sample_count': self.sample_count,
                'versions': {name: report.to_dict() for name, report in self.versions.items()}}
