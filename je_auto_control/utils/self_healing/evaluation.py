"""Evaluate locator versions on identical immutable frames with explicit labels."""
from __future__ import annotations

import math
import time
from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.self_healing.evaluation_models import (
    EvaluationSample, EvaluationTrial, HealingComparison, HealingEvaluationError,
    LocatorPrediction, LocatorStrategy, Point, VersionReport,
)


def evaluate_locators(samples: Sequence[EvaluationSample],
                      versions: Mapping[str, LocatorStrategy]) -> HealingComparison:
    """Compare supplied frames; no screenshots, clicks or guessed ground truth.

    Each strategy gets the same immutable sample. Errors retain their denominator
    and latency and cannot count as an expected miss. Rates distinguish labelled
    location recovery from independently annotated post-operation success.
    """
    if not versions or any(not isinstance(name, str) or not name for name in versions):
        raise HealingEvaluationError('at least one nonempty locator version is required')
    identifiers = [sample.sample_id or sample.frame_hash for sample in samples]
    if len(set(identifiers)) != len(identifiers):
        raise HealingEvaluationError('sample identities must be unique within a dataset')
    reports = {name: VersionReport(name, tuple(_evaluate_one(sample, strategy) for sample in samples))
               for name, strategy in versions.items()}
    return HealingComparison(len(samples), MappingProxyType(reports))


def _evaluate_one(sample: EvaluationSample, strategy: LocatorStrategy) -> EvaluationTrial:
    started = time.monotonic()
    error: Optional[str] = None
    try:
        prediction = strategy.locate(sample)
        if not isinstance(prediction, LocatorPrediction):
            raise HealingEvaluationError('strategy must return a LocatorPrediction')
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError, AttributeError) as failure:
        method = getattr(strategy, 'method', 'miss')
        prediction = LocatorPrediction(None, method if method in {'image', 'vlm', 'miss'} else 'miss')
        error = type(failure).__name__
    elapsed = max(0.0, (time.monotonic() - started) * 1000.0)
    coordinates = _to_desktop(prediction.coordinates, sample)
    expected_present = True if sample.expected_box is not None else False if sample.expected_miss else None
    correct = _correct(sample, coordinates, error)
    return EvaluationTrial(sample.sample_id or sample.frame_hash, sample.frame_hash, coordinates,
                           prediction.method, elapsed, correct, expected_present, error,
                           None,
                           prediction.backend, prediction.model, prediction.cost,
                           {'expected_box': list(sample.expected_box) if sample.expected_box is not None else None,
                            'expected_miss': sample.expected_miss, 'origin': list(sample.origin),
                            'scale': list(sample.scale), 'historical_operation_verified': sample.operation_verified,
                            'context': dict(sample.context) if sample.context else None})


def _to_desktop(point: Optional[Point], sample: EvaluationSample) -> Optional[Point]:
    if point is None:
        return None
    return (sample.origin[0] + math.floor(point[0] / sample.scale[0]),
            sample.origin[1] + math.floor(point[1] / sample.scale[1]))


def _correct(sample: EvaluationSample, point: Optional[Point], error: Optional[str]) -> Optional[bool]:
    if sample.expected_box is None and not sample.expected_miss:
        return None
    if error is not None:
        return False
    if sample.expected_miss:
        return point is None
    if point is None or sample.expected_box is None:
        return False
    left, top, width, height = sample.expected_box
    return left <= point[0] < left + width and top <= point[1] < top + height


__all__ = ['EvaluationSample', 'HealingComparison', 'HealingEvaluationError',
           'LocatorPrediction', 'LocatorStrategy', 'evaluate_locators']
