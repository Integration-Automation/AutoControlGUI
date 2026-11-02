"""Compare locator versions on identical provided frames with explicit quality populations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import floor
from time import perf_counter
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Sequence

from je_auto_control.utils.logging.secret_scope import scrub_secret_data, scrub_secret_text
from je_auto_control.utils.self_healing.evaluation_models import (
    EvaluationRatio, EvaluationSample, HealingAttempt, HealingEvaluationError,
    HealingVersionReport, LocatorCandidate, LocatorStrategy,
)


@dataclass(frozen=True)
class HealingComparison:
    """A comparison snapshot; JSON output is sanitized and contains no frame payloads."""

    versions: Mapping[str, HealingVersionReport]
    attempts: tuple[HealingAttempt, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "versions", MappingProxyType(dict(self.versions)))

    def to_dict(self) -> dict[str, object]:
        """Expose ratios, provenance and failures without dumping image bytes."""
        versions = {}
        for name, version in self.versions.items():
            values = asdict(version)
            for field_name in ("accuracy", "false_positive", "recovery", "image_hit", "fallback", "miss"):
                values[field_name] = getattr(version, field_name).to_dict()
            versions[name] = values
        result = {"schema_version": self.schema_version, "cost_unit": "USD", "versions": versions,
                  "attempts": [asdict(attempt) for attempt in self.attempts]}
        sanitized = scrub_secret_data(result)
        if not isinstance(sanitized, dict):
            raise HealingEvaluationError("comparison serialization must be an object")
        return sanitized


def evaluate_locators(samples: Sequence[EvaluationSample], versions: Mapping[str, LocatorStrategy], *,
                      observer: Optional[Callable[[int], None]] = None) -> HealingComparison:
    """Measure each version on the same immutable sample; never capture or operate a device.

    Wrong points and unexpected detections count as false positives among labelled
    predictions. Recovery requires both a correct located point and an explicit
    post-operation verification. Unknown labels/verification are excluded from the
    respective denominators. Latency percentiles use linear interpolation.
    Strategy exceptions (including cancellation) propagate, never count as misses.
    """
    bound_samples, bound_versions = tuple(samples), tuple(versions.items())
    _validate_comparison(bound_samples, bound_versions)
    attempts: list[HealingAttempt] = []
    if observer is not None:
        observer(0)
    for sample in bound_samples:
        digest = sha256(sample.frame).hexdigest()
        for version, strategy in bound_versions:
            if observer is not None:
                observer(len(attempts))
            started = perf_counter()
            candidate = strategy.locate(sample)
            elapsed = (perf_counter() - started) * 1000
            if not isinstance(candidate, LocatorCandidate):
                raise HealingEvaluationError("strategy must return LocatorCandidate")
            attempts.append(_attempt(sample, version, digest, candidate, elapsed))
            if observer is not None:
                observer(len(attempts))
    reports = {scrub_secret_text(name): _summarize([row for row in attempts if row.version == scrub_secret_text(name)])
               for name, _strategy in bound_versions}
    return HealingComparison(reports, tuple(attempts))


def _validate_comparison(samples: tuple[EvaluationSample, ...],
                         versions: tuple[tuple[str, LocatorStrategy], ...]) -> None:
    if not versions or len(versions) > 32 or len(samples) * len(versions) > 10000:
        raise HealingEvaluationError("comparison requires 1–32 versions and at most 10000 pairs")
    if any(not isinstance(sample, EvaluationSample) for sample in samples):
        raise HealingEvaluationError("samples must be EvaluationSample values")
    if len({scrub_secret_text(sample.sample_id) for sample in samples}) != len(samples):
        raise HealingEvaluationError("sample IDs must be unique")
    _validate_versions(versions)


def _validate_versions(versions: tuple[tuple[str, LocatorStrategy], ...]) -> None:
    for version, strategy in versions:
        if not isinstance(version, str) or not version.strip() or not callable(getattr(strategy, "locate", None)):
            raise HealingEvaluationError("versions require nonempty names and LocatorStrategy values")
    names = [scrub_secret_text(name) for name, _ in versions]
    if len(set(names)) != len(names):
        raise HealingEvaluationError("version names must stay distinct after secret masking")


def _attempt(sample: EvaluationSample, version: str, digest: str,
             candidate: LocatorCandidate, elapsed: float) -> HealingAttempt:
    correct = _correct(sample, candidate)
    clean_candidate = LocatorCandidate(
        candidate.coordinates, candidate.method, candidate.fallback_used, candidate.verified,
        scrub_secret_text(candidate.backend) if candidate.backend is not None else None,
        scrub_secret_text(candidate.model) if candidate.model is not None else None,
        candidate.cost, tuple((scrub_secret_text(name), duration) for name, duration in candidate.timings_ms))
    return HealingAttempt(scrub_secret_text(sample.sample_id), scrub_secret_text(version), digest, clean_candidate,
                          correct, correct is False and candidate.coordinates is not None, elapsed,
                          scrub_secret_text(sample.run_id) if sample.run_id is not None else None,
                          scrub_secret_text(sample.step_id) if sample.step_id is not None else None,
                          sample.expected_box, sample.expected_miss, sample.origin, sample.scale, sample.region)


def _correct(sample: EvaluationSample, candidate: LocatorCandidate) -> Optional[bool]:
    if sample.expected_miss:
        return candidate.coordinates is None
    if sample.expected_box is None:
        return None
    if candidate.coordinates is None:
        return False
    if sample.region is not None and not _inside(candidate.coordinates, sample.region):
        return False
    left, top, right, bottom = sample.expected_box
    x, y = candidate.coordinates
    return left <= x < right and top <= y < bottom


def _inside(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def _summarize(rows: list[HealingAttempt]) -> HealingVersionReport:
    quality = _quality(rows)
    activity = _activity(rows)
    costs = [row.candidate.cost for row in rows if row.candidate.cost is not None]
    durations = sorted(row.duration_ms for row in rows)
    return HealingVersionReport(
        len(rows), quality[0], quality[1], quality[2], quality[3],
        activity[0], activity[1], activity[2], quality[4],
        _percentile(durations, 0.5), _percentile(durations, 0.95), sum(costs) if costs else None, len(costs))


def _quality(rows: list[HealingAttempt]) -> tuple[int, EvaluationRatio, EvaluationRatio, EvaluationRatio, int]:
    labelled = [row for row in rows if row.correct is not None]
    predicted = [row for row in labelled if row.candidate.coordinates is not None]
    recovery, unknown = _recovery(rows)
    return (
        len(rows) - len(labelled),
        EvaluationRatio(sum(row.correct is True for row in labelled), len(labelled)),
        EvaluationRatio(sum(row.false_positive for row in predicted), len(predicted)),
        recovery, unknown)


def _recovery(rows: list[HealingAttempt]) -> tuple[EvaluationRatio, int]:
    fallback = [row for row in rows if row.candidate.fallback_used]
    verified = [row for row in fallback if row.correct is not None and row.candidate.verified is not None]
    return EvaluationRatio(sum(_recovered(row) for row in verified), len(verified)), len(fallback) - len(verified)


def _recovered(row: HealingAttempt) -> bool:
    return row.correct is True and row.candidate.coordinates is not None and row.candidate.verified is True


def _activity(rows: list[HealingAttempt]) -> tuple[EvaluationRatio, EvaluationRatio, EvaluationRatio]:
    return (
        EvaluationRatio(sum(row.candidate.method == "image" for row in rows), len(rows)),
        EvaluationRatio(sum(row.candidate.fallback_used for row in rows), len(rows)),
        EvaluationRatio(sum(row.candidate.coordinates is None for row in rows), len(rows)))


def _percentile(values: list[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = floor(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)
