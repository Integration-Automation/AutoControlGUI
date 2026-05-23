"""Prometheus-compatible metric primitives with a stdlib-only fallback.

The Prometheus exposition format is straightforward enough that
hand-rolling a writer is cheaper than pulling in ``prometheus_client``
as a hard dep. The shapes match the official library so an operator
can drop in ``prometheus_client`` later without rewriting call sites.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


_DEFAULT_HISTOGRAM_BUCKETS: Tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)
_LABEL_KEY_SEPARATOR = "\x1f"  # ASCII unit separator, can't appear in labels


def _validate_name(name: str, kind: str) -> None:
    """Prometheus naming: letters / digits / underscore, can't start with digit."""
    if not isinstance(name, str) or not name:
        raise ValueError(f"{kind} name must be a non-empty string")
    if not (name[0].isalpha() or name[0] == "_"):
        raise ValueError(f"{kind} name must start with letter or underscore")
    for ch in name:
        if not (ch.isalnum() or ch == "_"):
            raise ValueError(f"{kind} name contains illegal character: {ch!r}")


def _frozen_labels(labels: Optional[Dict[str, str]]) -> Tuple[Tuple[str, str], ...]:
    """Canonicalise a labels dict into a sortable tuple — keys sorted alphabetically."""
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _escape_label(value: str) -> str:
    """Prometheus text format requires \\, ", and newline escapes."""
    return (
        value.replace("\\", "\\\\")
             .replace("\"", "\\\"")
             .replace("\n", "\\n")
    )


def _render_label_pairs(pairs: Tuple[Tuple[str, str], ...]) -> str:
    if not pairs:
        return ""
    inner = ",".join(
        f'{k}="{_escape_label(v)}"' for k, v in pairs
    )
    return "{" + inner + "}"


@dataclass
class _MetricBase:
    name: str
    help_text: str
    label_names: Tuple[str, ...] = field(default_factory=tuple)


class Counter(_MetricBase):
    """Monotonically increasing counter.

    ``inc()`` adds ``amount`` (must be ≥ 0). Labels are validated against
    ``label_names`` so a typo doesn't quietly fork into a new series.
    """

    def __init__(self, name: str, help_text: str,
                 *, label_names: Sequence[str] = ()) -> None:
        _validate_name(name, "counter")
        for lname in label_names:
            _validate_name(lname, "label")
        super().__init__(name=name, help_text=help_text,
                          label_names=tuple(label_names))
        self._lock = threading.Lock()
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = {(): 0.0}

    def inc(self, amount: float = 1.0,
            *, labels: Optional[Dict[str, str]] = None) -> None:
        if amount < 0:
            raise ValueError("Counter increment must be non-negative")
        key = self._labels_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + float(amount)

    def value(self, *, labels: Optional[Dict[str, str]] = None) -> float:
        key = self._labels_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    def _labels_key(self, labels: Optional[Dict[str, str]]
                    ) -> Tuple[Tuple[str, str], ...]:
        if not self.label_names:
            return ()
        if not labels:
            raise ValueError(
                f"{self.name} expects labels {self.label_names}",
            )
        # Reject any label name not declared at registration.
        unknown = set(labels) - set(self.label_names)
        if unknown:
            raise ValueError(
                f"unknown labels {sorted(unknown)} for {self.name}",
            )
        return _frozen_labels(labels)

    def render(self) -> str:
        lines: List[str] = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            snapshot = dict(self._values)
        for key, value in snapshot.items():
            lines.append(f"{self.name}{_render_label_pairs(key)} {_fmt(value)}")
        return "\n".join(lines)


class Gauge(_MetricBase):
    """Free-floating numeric value (can go up and down)."""

    def __init__(self, name: str, help_text: str,
                 *, label_names: Sequence[str] = ()) -> None:
        _validate_name(name, "gauge")
        for lname in label_names:
            _validate_name(lname, "label")
        super().__init__(name=name, help_text=help_text,
                          label_names=tuple(label_names))
        self._lock = threading.Lock()
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = {(): 0.0}

    def set(self, value: float,
            *, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, amount: float = 1.0,
            *, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + float(amount)

    def dec(self, amount: float = 1.0,
            *, labels: Optional[Dict[str, str]] = None) -> None:
        self.inc(-amount, labels=labels)

    def value(self, *, labels: Optional[Dict[str, str]] = None) -> float:
        key = self._labels_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)

    _labels_key = Counter._labels_key  # same validation rules

    def render(self) -> str:
        lines: List[str] = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} gauge",
        ]
        with self._lock:
            snapshot = dict(self._values)
        for key, value in snapshot.items():
            lines.append(f"{self.name}{_render_label_pairs(key)} {_fmt(value)}")
        return "\n".join(lines)


@dataclass
class _HistogramSeries:
    bucket_counts: List[int]
    total_count: int = 0
    sum_value: float = 0.0


class Histogram(_MetricBase):
    """Observed-value distribution with configurable buckets."""

    def __init__(self, name: str, help_text: str,
                 *, label_names: Sequence[str] = (),
                 buckets: Sequence[float] = _DEFAULT_HISTOGRAM_BUCKETS) -> None:
        _validate_name(name, "histogram")
        for lname in label_names:
            _validate_name(lname, "label")
        if not buckets:
            raise ValueError("Histogram requires at least one bucket")
        # Buckets must be strictly increasing.
        last = -math.inf
        for boundary in buckets:
            if boundary <= last:
                raise ValueError("Histogram buckets must be strictly increasing")
            last = boundary
        super().__init__(name=name, help_text=help_text,
                          label_names=tuple(label_names))
        self._buckets: Tuple[float, ...] = tuple(buckets)
        self._lock = threading.Lock()
        self._series: Dict[Tuple[Tuple[str, str], ...], _HistogramSeries] = {}
        # Seed the no-label series for the common case.
        if not label_names:
            self._series[()] = self._empty_series()

    def observe(self, value: float,
                *, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            series = self._series.get(key)
            if series is None:
                series = self._empty_series()
                self._series[key] = series
            series.total_count += 1
            series.sum_value += float(value)
            for idx, boundary in enumerate(self._buckets):
                if value <= boundary:
                    series.bucket_counts[idx] += 1

    _labels_key = Counter._labels_key

    def snapshot(self, *, labels: Optional[Dict[str, str]] = None
                 ) -> Dict[str, object]:
        key = self._labels_key(labels)
        with self._lock:
            series = self._series.get(key) or self._empty_series()
            return {
                "buckets": list(zip(self._buckets, series.bucket_counts)),
                "count": series.total_count,
                "sum": series.sum_value,
            }

    def render(self) -> str:
        lines: List[str] = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            snapshot = {k: _HistogramSeries(
                bucket_counts=list(v.bucket_counts),
                total_count=v.total_count, sum_value=v.sum_value,
            ) for k, v in self._series.items()}
        for key, series in snapshot.items():
            label_str = _render_label_pairs(key)
            for boundary, count in zip(self._buckets, series.bucket_counts):
                bucket_label = self._render_bucket_label(key, boundary)
                lines.append(f"{self.name}_bucket{bucket_label} {count}")
            inf_label = self._render_bucket_label(key, math.inf)
            lines.append(f"{self.name}_bucket{inf_label} {series.total_count}")
            lines.append(f"{self.name}_count{label_str} {series.total_count}")
            lines.append(
                f"{self.name}_sum{label_str} {_fmt(series.sum_value)}",
            )
        return "\n".join(lines)

    def _empty_series(self) -> _HistogramSeries:
        return _HistogramSeries(
            bucket_counts=[0] * len(self._buckets),
        )

    @staticmethod
    def _render_bucket_label(key: Tuple[Tuple[str, str], ...],
                              boundary: float) -> str:
        le_value = "+Inf" if math.isinf(boundary) else _fmt(boundary)
        new_pairs = key + (("le", le_value),)
        return _render_label_pairs(new_pairs)


def _fmt(value: float) -> str:
    """Render a float the way Prometheus expects (no trailing zeroes)."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value == int(value):
        return str(int(value))
    return repr(float(value))


class MetricRegistry:
    """Process-wide registry. Collisions raise so a typo can't shadow a metric."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: Dict[str, _MetricBase] = {}

    def register(self, metric: _MetricBase) -> _MetricBase:
        with self._lock:
            existing = self._metrics.get(metric.name)
            if existing is not None:
                if type(existing) is not type(metric):
                    raise ValueError(
                        f"metric {metric.name!r} already registered as "
                        f"{type(existing).__name__}",
                    )
                return existing
            self._metrics[metric.name] = metric
            return metric

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._metrics.pop(name, None) is not None

    def get(self, name: str) -> Optional[_MetricBase]:
        with self._lock:
            return self._metrics.get(name)

    def list_metrics(self) -> Iterable[_MetricBase]:
        with self._lock:
            return list(self._metrics.values())

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()

    def render(self) -> str:
        return "\n".join(m.render() for m in self.list_metrics()) + "\n"


_default_registry: Optional[MetricRegistry] = None
_default_lock = threading.Lock()


def default_registry() -> MetricRegistry:
    """Process-wide singleton (lazy)."""
    global _default_registry
    with _default_lock:
        if _default_registry is None:
            _default_registry = MetricRegistry()
        return _default_registry


__all__ = [
    "Counter", "Gauge", "Histogram", "MetricRegistry", "default_registry",
]
