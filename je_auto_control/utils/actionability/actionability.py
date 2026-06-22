"""Pre-action readiness gate — visible + stable + enabled + not-occluded before acting.

Modern UI frameworks (Playwright, Cypress, WebdriverIO) auto-run an *actionability*
check before every click: the target must be present, have stopped moving, be enabled,
and actually receive the event (not be covered). AutoControl had none — ``self_heal_click``
locates and clicks immediately, and ``wait_until_screen_stable`` only watches the *whole*
frame. This composes the four checks into one gate.

Every signal is an injectable callable — ``bbox_provider`` (locate the target),
``region_sampler`` (pixel-stability token), ``enabled_probe`` (is it enabled?),
``hit_tester`` (is the click point on top?) — plus an injectable ``clock`` / ``sleep``,
so the gate is fully deterministic and headless-testable. Imports no ``PySide6``.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlActionException

Bbox = Tuple[int, int, int, int]
BboxProvider = Callable[[], Optional[Bbox]]


@dataclass
class GateConfig:
    """Timing knobs and test seams for the actionability gate."""

    timeout_s: float = 5.0
    stable_for_s: float = 0.3
    poll_interval_s: float = 0.1
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class ActionabilityReport:
    """The outcome of a gate: per-check booleans, the target point, and timing."""

    actionable: bool
    visible: bool
    stable: bool
    enabled: bool
    receives_events: bool
    waited_s: float
    reason: str
    point: Optional[List[int]] = None
    checks: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return the report as a plain dict."""
        return {"actionable": self.actionable, "visible": self.visible,
                "stable": self.stable, "enabled": self.enabled,
                "receives_events": self.receives_events, "waited_s": self.waited_s,
                "reason": self.reason, "point": self.point, "checks": self.checks}


def _center(bbox: Bbox) -> List[int]:
    return [bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2]


def _reason(visible: bool, stable: bool, enabled: bool, receives: bool) -> str:
    if not visible:
        return "not visible"
    if not stable:
        return "not stable"
    if not enabled:
        return "disabled"
    if not receives:
        return "occluded"
    return "actionable"


class _StabilityTracker:
    """Tracks how long the bbox (and optional pixel sample) has stayed unchanged."""

    def __init__(self, sampler, stable_for_s: float):
        self._sampler = sampler
        self._stable_for_s = stable_for_s
        self._prev: Any = object()
        self._since: Optional[float] = None

    def update(self, bbox: Optional[Bbox], now: float) -> bool:
        if bbox is None:
            self._since = None
            self._prev = object()
            return False
        token = (bbox, self._sampler(bbox) if self._sampler else None)
        if token != self._prev:
            self._prev = token
            self._since = now
            return False
        return (now - self._since) >= self._stable_for_s


def _evaluate(bbox, tracker, now, enabled_probe, hit_tester):
    """Return ``(visible, stable, enabled, receives, point)`` for one poll."""
    visible = bbox is not None
    stable = tracker.update(bbox, now)
    enabled = enabled_probe is None or bool(enabled_probe())
    point = _center(bbox) if visible else None
    receives = hit_tester is None or point is None or bool(hit_tester(point))
    return visible, stable, enabled, receives, point


def _report(visible, stable, enabled, receives, point, waited):
    actionable = visible and stable and enabled and receives
    return ActionabilityReport(
        actionable, visible, stable, enabled, receives, round(waited, 4),
        _reason(visible, stable, enabled, receives), point,
        {"visible": visible, "stable": stable, "enabled": enabled,
         "receives_events": receives})


def wait_actionable(bbox_provider: BboxProvider, *,
                    region_sampler: Optional[Callable[[Bbox], Any]] = None,
                    enabled_probe: Optional[Callable[[], Optional[bool]]] = None,
                    hit_tester: Optional[Callable[[List[int]], bool]] = None,
                    config: Optional[GateConfig] = None) -> ActionabilityReport:
    """Poll until the target is visible + stable + enabled + unoccluded, or timeout.

    ``bbox_provider`` returns the target ``(x, y, w, h)`` or ``None``. The optional
    ``region_sampler`` returns a pixel token over the bbox (movement/animation
    settling); ``enabled_probe`` reports enabled state; ``hit_tester`` reports
    whether the centre point is on top. Returns an :class:`ActionabilityReport`.
    """
    cfg = config or GateConfig()
    tracker = _StabilityTracker(region_sampler, cfg.stable_for_s)
    start = cfg.clock()
    deadline = start + cfg.timeout_s
    while True:
        now = cfg.clock()
        signals = _evaluate(bbox_provider(), tracker, now, enabled_probe,
                            hit_tester)
        report = _report(*signals, now - start)
        if report.actionable or now >= deadline:
            return report
        cfg.sleep(cfg.poll_interval_s)


def act_when_ready(action: Callable[[List[int]], Any], bbox_provider: BboxProvider,
                   *, region_sampler: Optional[Callable[[Bbox], Any]] = None,
                   enabled_probe: Optional[Callable[[], Optional[bool]]] = None,
                   hit_tester: Optional[Callable[[List[int]], bool]] = None,
                   config: Optional[GateConfig] = None) -> Any:
    """Wait for the target to be actionable, then call ``action(center_point)``.

    Raises ``AutoControlActionException`` (with the failing check) if the gate times
    out before the target becomes actionable.
    """
    report = wait_actionable(bbox_provider, region_sampler=region_sampler,
                             enabled_probe=enabled_probe, hit_tester=hit_tester,
                             config=config)
    if not report.actionable:
        raise AutoControlActionException(
            f"target not actionable ({report.reason}) after {report.waited_s}s")
    return action(report.point)
