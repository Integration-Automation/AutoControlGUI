"""Decide when a UI has settled, as a pure seam over a churn series.

``smart_waits.wait_until_screen_stable`` and ``actionability``'s stability check bake the
settle logic *inside* a ``time.sleep`` polling loop over live pixel frames — you cannot feed
them a recorded series of a11y-element counts or screen-diff metrics, and you cannot unit-test
the *decision* independently of capture. ``settle_detector`` extracts that decision: it takes a
stream of *churn* values (how much changed each sample — pixel delta, element-count delta, a
digest-changed 0/1, anything) and reports when the churn has stayed at or below ``max_churn``
for ``quiet_samples`` in a row. A spike resets the quiet run, so "settled then changed again"
is handled.

Pure-stdlib; deterministic and unit-testable on an injected series with no capture, no clock.
Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Sequence


@dataclass(frozen=True)
class SettleState:
    """One settle observation: whether settled, the quiet run length, latest churn."""

    settled: bool
    quiet_run: int
    churn: float

    def to_dict(self) -> Dict[str, Any]:
        """Return the state as a plain dict."""
        return asdict(self)


class SettleTracker:
    """Incremental settle detector: feed churn values, ask if it has gone quiet."""

    def __init__(self, quiet_samples: int = 3, max_churn: float = 1.0) -> None:
        """Settle after ``quiet_samples`` consecutive churns <= ``max_churn``."""
        self.quiet_samples = int(quiet_samples)
        self.max_churn = float(max_churn)
        self.quiet_run = 0

    def update(self, churn: float) -> SettleState:
        """Feed the next churn value and return the current settle state."""
        churn = float(churn)
        if churn <= self.max_churn:
            self.quiet_run += 1
        else:
            self.quiet_run = 0
        return SettleState(self.quiet_run >= self.quiet_samples, self.quiet_run,
                           churn)

    def reset(self) -> None:
        """Clear the quiet run (e.g. after acting again)."""
        self.quiet_run = 0


def settle_point(churns: Sequence[float], *, quiet_samples: int = 3,
                 max_churn: float = 1.0) -> Optional[int]:
    """Return the index at which the churn series first becomes settled, or ``None``."""
    tracker = SettleTracker(quiet_samples, max_churn)
    for index, churn in enumerate(churns):
        if tracker.update(churn).settled:
            return index
    return None


def is_settled(churns: Sequence[float], *, quiet_samples: int = 3,
               max_churn: float = 1.0) -> bool:
    """Return whether the churn series settles at any point."""
    return settle_point(churns, quiet_samples=quiet_samples,
                        max_churn=max_churn) is not None
