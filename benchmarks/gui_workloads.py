"""Passive catalog reports and repeatable, input-free GUI script workloads."""
from __future__ import annotations

import json
import math
from typing import Any, Protocol


class CatalogWorkspace(Protocol):
    """Existing widget catalog API used by the benchmark and parity probes."""

    def list_registered_tabs(self) -> list[dict[str, Any]]:
        """Return ordered passive metadata."""

    def show_tab(self, key: str) -> None:
        """Open an explicitly selected feature."""


def catalog_report(workspace: CatalogWorkspace) -> dict[str, object]:
    """Read the full metadata catalog without constructing unopened features."""
    rows = workspace.list_registered_tabs()
    return {'registered_keys': [row['key'] for row in rows],
            'default_keys': [row['key'] for row in rows if row['visible']]}


def percentile95(samples: list[float]) -> float:
    """Use the nearest-rank percentile consistently across before/after runs."""
    if not samples:
        raise ValueError('latency sampling produced no events')
    return sorted(samples)[max(0, math.ceil(len(samples) * .95) - 1)]


def waiting_script(seconds: float) -> str:
    """A real executor workload with no desktop/device/network side effects."""
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('workload duration must be positive and finite')
    return json.dumps([['AC_sleep', {'seconds': seconds}]])


def recovery_report(reason: object) -> dict[str, object]:
    """Report an explicit unavailable-feature reason without a permission probe."""
    return {'unsupported_feature_has_reason': isinstance(reason, str) and bool(reason.strip())}
