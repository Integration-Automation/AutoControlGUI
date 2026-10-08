"""Measure locator strategy versions against the same labelled frames.

The heal log answers "what did the locator do"; it cannot answer "was that
right", because a strategy that returns a confident wrong point looks exactly
like one that healed. This module compares strategy versions on samples that
carry the answer:

* every version is called with the **same** :class:`LocateRequest` — one
  captured frame, one region, one origin and scale — so a difference between
  two reports is a difference between two strategies and never between two
  screenshots. A strategy that edits the frame in place is refused, since the
  next version would be measured on something else;
* a hit is ``correct`` only when it lands inside the sample's ``expected_box``.
  A hit anywhere else, or on a sample that expects a miss, is a
  ``false_positive`` — it is located, and it is not a recovery;
* a sample with no label is ``unknown``. It counts in the hit rate, where no
  label is needed, and in no rate that claims correctness;
* every rate is a :class:`Ratio` carrying its numerator and denominator, and a
  rate over nothing has no value rather than a perfect one;
* a strategy that calls a model carries a :class:`UsageMeter` as its
  ``usage_meter`` attribute. Its calls are counted per sample and per version;
  tokens and cost are reported only where the backend reported them, and are
  ``None`` -- not zero -- where it did not.

All coordinates are screen coordinates. ``origin`` is the screen position of
the frame's top-left pixel (negative on a monitor left of or above the
primary) and ``scale`` is frame pixels per screen unit, so a frame pixel
``(fx, fy)`` is the screen point ``(origin_x + fx / scale, origin_y + fy /
scale)``. :meth:`LocateRequest.to_screen` and :meth:`LocateRequest.frame_box`
do that arithmetic for a strategy.

Qt-free and capture-free: nothing here reads the screen.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from time import perf_counter
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple,
)

from je_auto_control.utils.exception.exceptions import AutoControlException

Box = Tuple[int, int, int, int]
Point = Tuple[int, int]

OUTCOME_CORRECT = "correct"
OUTCOME_FALSE_POSITIVE = "false_positive"
OUTCOME_MISS = "miss"
OUTCOME_TRUE_NEGATIVE = "true_negative"
OUTCOME_UNKNOWN = "unknown"
OUTCOME_ERROR = "error"

#: Outcomes that are a failure of the strategy on a labelled sample.
FAILURE_OUTCOMES = (OUTCOME_FALSE_POSITIVE, OUTCOME_MISS, OUTCOME_ERROR)

_STRATEGY_ERRORS = (AutoControlException, OSError, RuntimeError, ValueError,
                    TypeError, ArithmeticError, LookupError)


class HealingEvaluationError(AutoControlException, ValueError):
    """An evaluation was set up so that its result could not be trusted."""


def _as_box(value: Optional[Sequence[int]], name: str) -> Optional[Box]:
    if value is None:
        return None
    try:
        x1, y1, x2, y2 = (int(item) for item in value)
    except (TypeError, ValueError) as error:
        raise HealingEvaluationError(
            f"{name} must be [x1, y1, x2, y2]; got {value!r}") from error
    if x2 <= x1 or y2 <= y1:
        raise HealingEvaluationError(
            f"{name} must have x2 > x1 and y2 > y1; got {value!r}")
    return x1, y1, x2, y2


def _as_point(value: Sequence[int], name: str) -> Point:
    try:
        x, y = (int(item) for item in value)
    except (TypeError, ValueError) as error:
        raise HealingEvaluationError(f"{name} must be [x, y]; got {value!r}") from error
    return x, y


def frame_hash(frame: Any) -> Optional[str]:
    """SHA-256 of ``frame``'s pixels and shape; ``None`` for an unhashable frame."""
    if isinstance(frame, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(frame)).hexdigest()
    to_bytes = getattr(frame, "tobytes", None)
    if to_bytes is None:
        return None
    digest = hashlib.sha256(repr(getattr(frame, "shape", None)).encode("ascii"))
    digest.update(to_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class EvaluationSample:
    """One captured frame and what a correct locator returns for it.

    ``expected_box`` and ``region`` are ``(x1, y1, x2, y2)`` in screen
    coordinates. A sample with neither ``expected_box`` nor ``expect_miss`` is
    unlabelled and is reported as ``unknown``.
    """

    sample_id: str
    frame: Any
    expected_box: Optional[Box] = None
    origin: Point = (0, 0)
    scale: float = 1.0
    region: Optional[Box] = None
    expect_miss: bool = False
    template: Any = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected_box", _as_box(self.expected_box, "expected_box"))
        object.__setattr__(self, "region", _as_box(self.region, "region"))
        object.__setattr__(self, "origin", _as_point(self.origin, "origin"))
        try:
            scale = float(self.scale)
        except (TypeError, ValueError) as error:
            raise HealingEvaluationError(f"scale must be a number; got {self.scale!r}") from error
        if not math.isfinite(scale) or scale <= 0:
            raise HealingEvaluationError(f"scale must be positive; got {self.scale!r}")
        object.__setattr__(self, "scale", scale)
        if self.expect_miss and self.expected_box is not None:
            raise HealingEvaluationError(
                f"sample {self.sample_id!r}: expect_miss and expected_box contradict")

    @property
    def labelled(self) -> bool:
        """Whether the sample says what the right answer is."""
        return self.expect_miss or self.expected_box is not None


@dataclass(frozen=True)
class LocateRequest:
    """What every strategy version receives for one sample — the same object."""

    sample_id: str
    frame: Any
    origin: Point
    scale: float
    region: Optional[Box]
    template: Any
    description: Optional[str]
    frame_hash: Optional[str]

    def to_screen(self, frame_x: float, frame_y: float) -> Point:
        """A frame pixel as the screen point a click would be sent to."""
        return (self.origin[0] + int(math.floor(frame_x / self.scale)),
                self.origin[1] + int(math.floor(frame_y / self.scale)))

    def frame_box(self, width: int, height: int) -> Optional[Box]:
        """``region`` in frame pixels, clipped to a ``width`` x ``height`` frame.

        The whole frame when there is no region; ``None`` when the region does
        not overlap the frame, which a strategy must treat as nothing to search.
        """
        if self.region is None:
            return 0, 0, int(width), int(height)
        x1, y1, x2, y2 = self.region
        left = max(0, int(math.floor((x1 - self.origin[0]) * self.scale)))
        top = max(0, int(math.floor((y1 - self.origin[1]) * self.scale)))
        right = min(int(width), int(math.ceil((x2 - self.origin[0]) * self.scale)))
        bottom = min(int(height), int(math.ceil((y2 - self.origin[1]) * self.scale)))
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom


#: A strategy version: screen ``(x, y)`` for a hit, ``None`` for a miss.
LocatorStrategy = Callable[[LocateRequest], Optional[Sequence[int]]]


def _plus(left: Optional[float], right: Optional[float]) -> Optional[float]:
    """Sum where ``None`` means "not reported", not zero."""
    if left is None:
        return right
    return left if right is None else left + right


@dataclass(frozen=True)
class ModelUsage:
    """Model calls made, and the tokens / cost the backend reported for them.

    ``input_tokens``, ``output_tokens`` and ``cost`` are ``None`` when no call
    reported them. ``cost`` is in whatever currency the price was given in.
    """

    calls: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost: Optional[float] = None

    def plus(self, other: "ModelUsage") -> "ModelUsage":
        """This usage and ``other`` added together."""
        tokens_in = _plus(self.input_tokens, other.input_tokens)
        tokens_out = _plus(self.output_tokens, other.output_tokens)
        return ModelUsage(
            self.calls + other.calls,
            None if tokens_in is None else int(tokens_in),
            None if tokens_out is None else int(tokens_out),
            _plus(self.cost, other.cost))

    def to_dict(self) -> Dict[str, Any]:
        """``{model_calls, input_tokens, output_tokens, cost}``."""
        return {"model_calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost": None if self.cost is None else round(self.cost, 6)}


class UsageMeter:
    """Collects what a model-calling strategy used since it was last drained.

    A strategy records each call with :meth:`record`; the evaluation drains
    the meter after every sample, so usage lands on the sample that caused it.
    """

    def __init__(self) -> None:
        self._pending = ModelUsage()

    def record(self, usage: ModelUsage) -> None:
        """Add one or more calls' usage."""
        self._pending = self._pending.plus(usage)

    def drain(self) -> ModelUsage:
        """Return what was recorded since the last drain, and reset."""
        pending, self._pending = self._pending, ModelUsage()
        return pending


def _drain_usage(strategy: Any) -> ModelUsage:
    meter = getattr(strategy, "usage_meter", None)
    return meter.drain() if isinstance(meter, UsageMeter) else ModelUsage()


@dataclass(frozen=True)
class Ratio:
    """A rate that keeps the counts it was computed from."""

    numerator: int
    denominator: int

    @property
    def value(self) -> Optional[float]:
        """The rate, or ``None`` when there was nothing to divide by."""
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    def to_dict(self) -> Dict[str, Any]:
        """``{numerator, denominator, value}``; ``value`` is ``None`` over zero."""
        value = self.value
        return {"numerator": self.numerator, "denominator": self.denominator,
                "value": None if value is None else round(value, 4)}

    def __str__(self) -> str:
        value = self.value
        shown = "n/a" if value is None else f"{value * 100:.1f}%"
        return f"{self.numerator}/{self.denominator} ({shown})"


@dataclass(frozen=True)
class SampleResult:
    """What one strategy version did with one sample."""

    sample_id: str
    version: str
    outcome: str
    located: bool
    coordinates: Optional[Point]
    latency_ms: float
    frame_hash: Optional[str]
    error: Optional[str] = None
    usage: ModelUsage = ModelUsage()

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe row."""
        return {
            "sample_id": self.sample_id, "version": self.version,
            "outcome": self.outcome, "located": self.located,
            "coordinates": None if self.coordinates is None else list(self.coordinates),
            "latency_ms": self.latency_ms, "frame_hash": self.frame_hash,
            "error": self.error, **self.usage.to_dict(),
        }


@dataclass(frozen=True)
class VersionReport:
    """Counts for one strategy version; the six outcomes add up to ``total``."""

    version: str
    total: int
    located: int
    correct: int
    false_positive: int
    miss: int
    true_negative: int
    unknown: int
    error: int
    recovered: int
    recoverable: int
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    usage: ModelUsage = ModelUsage()

    @property
    def labelled(self) -> int:
        """Samples that say what the right answer is."""
        return self.total - self.unknown

    @property
    def hit_rate(self) -> Ratio:
        """Samples a point was returned for, right or wrong, over all samples."""
        return Ratio(self.located, self.total)

    @property
    def accuracy(self) -> Ratio:
        """Correct hits plus correct rejections, over labelled samples."""
        return Ratio(self.correct + self.true_negative, self.labelled)

    @property
    def false_positive_rate(self) -> Ratio:
        """Hits in the wrong place or on an expected miss, over labelled samples."""
        return Ratio(self.false_positive, self.labelled)

    @property
    def recovery_rate(self) -> Ratio:
        """Targets the baseline failed on that this version hit correctly."""
        return Ratio(self.recovered, self.recoverable)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe report; every rate carries numerator and denominator."""
        return {
            "version": self.version, "total": self.total,
            "labelled": self.labelled, "located": self.located,
            "correct": self.correct, "false_positive": self.false_positive,
            "miss": self.miss, "true_negative": self.true_negative,
            "unknown": self.unknown, "error": self.error,
            "hit_rate": self.hit_rate.to_dict(),
            "accuracy": self.accuracy.to_dict(),
            "false_positive_rate": self.false_positive_rate.to_dict(),
            "recovery_rate": self.recovery_rate.to_dict(),
            "p50_ms": self.p50_ms, "p95_ms": self.p95_ms,
            **self.usage.to_dict(),
        }


@dataclass(frozen=True)
class HealingComparison:
    """Reports for every version over one set of samples."""

    baseline: str
    reports: Mapping[str, VersionReport]
    results: Tuple[SampleResult, ...]

    def report(self, version: str) -> VersionReport:
        """The report for ``version``; unknown names raise."""
        try:
            return self.reports[version]
        except KeyError:
            raise HealingEvaluationError(
                f"no such version {version!r}; have {list(self.reports)}") from None

    def failures(self, version: str) -> List[SampleResult]:
        """Labelled samples ``version`` got wrong, in sample order."""
        self.report(version)
        return [row for row in self.results
                if row.version == version and row.outcome in FAILURE_OUTCOMES]

    def to_dict(self) -> Dict[str, Any]:
        """The whole comparison as JSON-safe data."""
        return {
            "baseline": self.baseline,
            "versions": {name: report.to_dict() for name, report in self.reports.items()},
            "results": [row.to_dict() for row in self.results],
        }


def evaluate_locators(samples: Sequence[EvaluationSample],
                      versions: Mapping[str, LocatorStrategy],
                      *, baseline: Optional[str] = None,
                      clock: Callable[[], float] = perf_counter,
                      ) -> HealingComparison:
    """Run every strategy in ``versions`` over every sample and score it.

    ``baseline`` names the version recovery is measured against; it defaults
    to the first one. ``clock`` returns seconds and exists so a test can make
    the latency columns deterministic.
    """
    names = list(versions)
    if not names:
        raise HealingEvaluationError("evaluate_locators needs at least one version")
    base = names[0] if baseline is None else baseline
    if base not in versions:
        raise HealingEvaluationError(f"baseline {base!r} is not one of {names}")
    _reject_duplicate_ids(samples)
    rows: List[SampleResult] = []
    for sample in samples:
        request = LocateRequest(
            sample_id=sample.sample_id, frame=sample.frame, origin=sample.origin,
            scale=sample.scale, region=sample.region, template=sample.template,
            description=sample.description, frame_hash=frame_hash(sample.frame))
        for name in names:
            rows.append(_run_one(sample, request, name, versions[name], clock))
    reports = _build_reports(samples, names, base, rows)
    return HealingComparison(baseline=base, reports=reports, results=tuple(rows))


def _reject_duplicate_ids(samples: Sequence[EvaluationSample]) -> None:
    seen = set()
    for sample in samples:
        if sample.sample_id in seen:
            raise HealingEvaluationError(f"duplicate sample id {sample.sample_id!r}")
        seen.add(sample.sample_id)


def _run_one(sample: EvaluationSample, request: LocateRequest, version: str,
             strategy: LocatorStrategy, clock: Callable[[], float]) -> SampleResult:
    _drain_usage(strategy)  # nothing an earlier caller left behind counts here
    started = clock()
    point: Optional[Point] = None
    error: Optional[str] = None
    try:
        raw = strategy(request)
        point = None if raw is None else _as_point(raw, f"{version} result")
    except _STRATEGY_ERRORS as exc:
        error = repr(exc)
    latency = round((clock() - started) * 1000.0, 3)
    if frame_hash(sample.frame) != request.frame_hash:
        raise HealingEvaluationError(
            f"version {version!r} modified the frame of sample {sample.sample_id!r}; "
            "later versions would be measured on a different image")
    return SampleResult(
        sample_id=sample.sample_id, version=version,
        outcome=_classify(sample, point, error), located=point is not None,
        coordinates=point, latency_ms=latency, frame_hash=request.frame_hash,
        error=error, usage=_drain_usage(strategy))


def _classify(sample: EvaluationSample, point: Optional[Point],
              error: Optional[str]) -> str:
    if not sample.labelled:
        return OUTCOME_UNKNOWN
    if error is not None:
        return OUTCOME_ERROR
    if point is None:
        return OUTCOME_TRUE_NEGATIVE if sample.expect_miss else OUTCOME_MISS
    if sample.expected_box is not None and _inside(point, sample.expected_box):
        return OUTCOME_CORRECT
    return OUTCOME_FALSE_POSITIVE


def _inside(point: Point, box: Box) -> bool:
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def _build_reports(samples: Sequence[EvaluationSample], names: Sequence[str],
                   baseline: str, rows: Sequence[SampleResult],
                   ) -> Dict[str, VersionReport]:
    by_version: Dict[str, Dict[str, SampleResult]] = {name: {} for name in names}
    for row in rows:
        by_version[row.version][row.sample_id] = row
    # Recoverable: a target that exists and that the baseline did not hit
    # correctly. An expected miss is never in this set.
    recoverable = [sample.sample_id for sample in samples
                   if sample.expected_box is not None
                   and by_version[baseline][sample.sample_id].outcome != OUTCOME_CORRECT]
    reports: Dict[str, VersionReport] = {}
    for name in names:
        own = by_version[name]
        recovered = sum(1 for sample_id in recoverable
                        if own[sample_id].outcome == OUTCOME_CORRECT)
        reports[name] = _report(name, list(own.values()), recovered, len(recoverable))
    return reports


def _report(version: str, rows: Sequence[SampleResult], recovered: int,
            recoverable: int) -> VersionReport:
    counts = {outcome: 0 for outcome in (
        OUTCOME_CORRECT, OUTCOME_FALSE_POSITIVE, OUTCOME_MISS,
        OUTCOME_TRUE_NEGATIVE, OUTCOME_UNKNOWN, OUTCOME_ERROR)}
    for row in rows:
        counts[row.outcome] += 1
    latencies = sorted(row.latency_ms for row in rows)
    usage = ModelUsage()
    for row in rows:
        usage = usage.plus(row.usage)
    return VersionReport(
        usage=usage,
        version=version, total=len(rows),
        located=sum(1 for row in rows if row.located),
        correct=counts[OUTCOME_CORRECT],
        false_positive=counts[OUTCOME_FALSE_POSITIVE],
        miss=counts[OUTCOME_MISS], true_negative=counts[OUTCOME_TRUE_NEGATIVE],
        unknown=counts[OUTCOME_UNKNOWN], error=counts[OUTCOME_ERROR],
        recovered=recovered, recoverable=recoverable,
        p50_ms=_percentile(latencies, 50), p95_ms=_percentile(latencies, 95))


def _percentile(ordered: Sequence[float], percent: int) -> Optional[float]:
    """Nearest-rank percentile of an ascending list; ``None`` when it is empty."""
    if not ordered:
        return None
    rank = max(1, math.ceil(percent / 100.0 * len(ordered)))
    return ordered[rank - 1]


_THRESHOLD_CHECKS: Dict[str, Callable[[VersionReport], Optional[float]]] = {
    "min_correct": lambda report: report.correct,
    "min_accuracy": lambda report: report.accuracy.value,
    "max_false_positive": lambda report: report.false_positive,
    "max_error": lambda report: report.error,
    "max_p95_ms": lambda report: report.p95_ms,
    "max_model_calls": lambda report: report.usage.calls,
    "max_cost": lambda report: report.usage.cost,
}


def check_thresholds(comparison: HealingComparison,
                     thresholds: Mapping[str, Mapping[str, float]]) -> List[str]:
    """Return one line per threshold ``comparison`` does not meet.

    ``thresholds`` maps a version to ``min_correct`` / ``min_accuracy`` /
    ``max_false_positive`` / ``max_error`` / ``max_p95_ms`` /
    ``max_model_calls`` / ``max_cost``. A version or key
    that does not exist is a violation too: a gate that silently checks
    nothing is worse than none. A rate with no value fails its ``min_``.
    """
    violations: List[str] = []
    for version, limits in thresholds.items():
        report = comparison.reports.get(version)
        if report is None:
            violations.append(f"{version}: no such version in the comparison")
            continue
        for key, limit in limits.items():
            problem = _threshold_problem(report, key, limit)
            if problem:
                violations.append(f"{version}: {problem}")
    return violations


def _threshold_problem(report: VersionReport, key: str, limit: float) -> Optional[str]:
    reader = _THRESHOLD_CHECKS.get(key)
    if reader is None:
        return f"unknown threshold {key!r}"
    measured = reader(report)
    if key.startswith("min_"):
        failed = measured is None or measured < limit
    else:
        failed = measured is not None and measured > limit
    return f"{key}={limit} not met (measured {measured})" if failed else None


def format_comparison(comparison: HealingComparison) -> str:
    """Plain-text table of the comparison, followed by each version's failures."""
    lines = [f"baseline: {comparison.baseline}"]
    for name, report in comparison.reports.items():
        lines.append(
            f"[{name}] samples={report.total} labelled={report.labelled} "
            f"unknown={report.unknown} error={report.error}")
        lines.append(f"  located      {report.hit_rate}")
        lines.append(f"  accuracy     {report.accuracy}")
        lines.append(f"  false pos.   {report.false_positive_rate}")
        lines.append(f"  recovery     {report.recovery_rate}")
        lines.append(f"  latency ms   p50={report.p50_ms} p95={report.p95_ms}")
        if report.usage.calls:
            used = report.usage
            lines.append(
                f"  model calls  {used.calls} tokens in={used.input_tokens} "
                f"out={used.output_tokens} cost={used.cost}")
        for row in comparison.failures(name):
            where = "" if row.coordinates is None else f" at {list(row.coordinates)}"
            reason = "" if row.error is None else f" ({row.error})"
            lines.append(f"  ! {row.sample_id}: {row.outcome}{where}{reason}")
    return "\n".join(lines)


__all__ = [
    "Box", "EvaluationSample", "FAILURE_OUTCOMES", "HealingComparison",
    "HealingEvaluationError", "LocateRequest", "LocatorStrategy",
    "OUTCOME_CORRECT", "OUTCOME_ERROR", "OUTCOME_FALSE_POSITIVE",
    "ModelUsage", "OUTCOME_MISS", "OUTCOME_TRUE_NEGATIVE", "OUTCOME_UNKNOWN",
    "Point", "Ratio", "SampleResult", "UsageMeter", "VersionReport",
    "check_thresholds", "evaluate_locators", "format_comparison", "frame_hash",
]
