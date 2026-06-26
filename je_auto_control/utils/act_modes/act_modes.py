"""Trial and force action modes over the actionability gate (Playwright-style).

``actionability.act_when_ready`` has one behaviour: wait for the target to be
actionable, then act (or raise on timeout). Real flows need two more modes that
Playwright codified:

* **trial** — run every actionability check but *don't* perform the action; just
  report whether it *would* have acted. The dry-run for "is this control ready?"
  without side effects.
* **force** — skip the checks and act *now*, for the deliberate escape hatch when
  the gate is wrong (a control the heuristics misjudge as occluded / disabled).

``act_with_mode`` adds both alongside the default gated behaviour, over the same
injectable seams as the gate, so each mode is testable without a screen. Reuses
:func:`actionability.wait_actionable`. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.actionability import wait_actionable
from je_auto_control.utils.actionability.actionability import _center

# The supported action modes.
ACT_MODES = ("auto", "trial", "force")


def _force_act(action: Callable[[List[int]], Any],
               bbox_provider: Callable[[], Any]) -> Dict[str, Any]:
    """Act at the target centre with no actionability checks."""
    bbox = bbox_provider()
    if not bbox:
        return {"mode": "force", "acted": False, "actionable": True,
                "reason": "no target", "point": None, "result": None}
    point = _center(bbox)
    return {"mode": "force", "acted": True, "actionable": True,
            "reason": "forced", "point": point, "result": action(point)}


def act_with_mode(action: Callable[[List[int]], Any],
                  bbox_provider: Callable[[], Any], *, mode: str = "auto",
                  region_sampler: Optional[Callable[[Any], Any]] = None,
                  enabled_probe: Optional[Callable[[], Optional[bool]]] = None,
                  hit_tester: Optional[Callable[[List[int]], bool]] = None,
                  config: Optional[Any] = None) -> Dict[str, Any]:
    """Perform ``action`` on a target under a ``mode`` (auto / trial / force).

    ``auto`` waits for the actionability gate and acts only if it passes;
    ``trial`` runs the gate but never acts (a dry run); ``force`` acts at once
    with no checks. Returns ``{mode, acted, actionable, reason, point, result}``.
    Raises ``ValueError`` for an unknown ``mode``.
    """
    if mode not in ACT_MODES:
        raise ValueError(f"unknown act mode: {mode!r}")
    if mode == "force":
        return _force_act(action, bbox_provider)
    report = wait_actionable(bbox_provider, region_sampler=region_sampler,
                             enabled_probe=enabled_probe, hit_tester=hit_tester,
                             config=config)
    point = list(report.point) if report.point is not None else None
    base = {"mode": mode, "actionable": report.actionable,
            "reason": report.reason, "point": point}
    if mode == "trial" or not report.actionable:
        return {**base, "acted": False, "result": None}
    return {**base, "acted": True, "result": action(report.point)}
