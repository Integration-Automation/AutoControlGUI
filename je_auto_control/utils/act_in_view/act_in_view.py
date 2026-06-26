"""Scroll a target into view, then act on it only once it is actionable.

Two reliability primitives the framework already had stayed separate:
``scroll_find.scroll_until_visible`` brings an off-screen target on-screen, and
``actionability.act_when_ready`` waits for a target to be visible / stable /
enabled / unoccluded before acting. A real "click the row three pages down" step
needs *both* — scroll to it, then gate before clicking. ``act_in_view`` composes
them into one call.

* :class:`ScrollPlan` — bundles the scroll search (``kind`` / ``direction`` /
  ``max_scrolls`` / ``scroll_amount``) and its injectable ``locator`` /
  ``scroller`` seams, so the composed call stays within a sane argument count.
* :func:`act_in_view` — scroll until the target is found, then run the
  actionability gate at its location and perform ``action`` on it.

All seams (locator / scroller / action / actionability probes / clock) are
injectable, so the whole flow is testable without a screen. Reuses
:func:`scroll_find.scroll_until_visible` and
:func:`actionability.act_when_ready`. Imports no ``PySide6``.
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.actionability import GateConfig, act_when_ready
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.scroll_find import scroll_until_visible
from je_auto_control.utils.scroll_find.scroll_find import Locator, Scroller


@dataclass
class ScrollPlan:
    """How to scroll while searching for the target (with injectable seams)."""

    kind: str = "image"
    direction: str = "down"
    max_scrolls: int = 10
    scroll_amount: int = 3
    locator: Optional[Locator] = None
    scroller: Optional[Scroller] = None


def act_in_view(target: str, action: Callable[[List[int]], Any], *,
                scroll: Optional[ScrollPlan] = None,
                region_sampler: Optional[Callable[[Any], Any]] = None,
                enabled_probe: Optional[Callable[[], Optional[bool]]] = None,
                hit_tester: Optional[Callable[[List[int]], bool]] = None,
                config: Optional[GateConfig] = None) -> Dict[str, Any]:
    """Scroll ``target`` into view, gate on actionability, then ``action`` it.

    Scrolls per ``scroll`` (a :class:`ScrollPlan`) until ``target`` is located,
    then runs :func:`actionability.act_when_ready` at the found point and calls
    ``action(center_point)``. Raises ``AutoControlActionException`` if the target
    never comes into view. The actionability probes / ``config`` are injectable
    and forwarded to the gate. Returns ``{acted, coords, scrolls, result}``.
    """
    plan = scroll if scroll is not None else ScrollPlan()
    found = scroll_until_visible(
        target, kind=plan.kind, direction=plan.direction,
        max_scrolls=plan.max_scrolls, scroll_amount=plan.scroll_amount,
        locator=plan.locator, scroller=plan.scroller)
    if not found["found"]:
        raise AutoControlActionException(
            f"target {target!r} not in view after {found['scrolls']} scrolls")
    cx, cy = int(found["coords"][0]), int(found["coords"][1])
    result = act_when_ready(action, lambda: (cx, cy, 1, 1),
                            region_sampler=region_sampler,
                            enabled_probe=enabled_probe, hit_tester=hit_tester,
                            config=config)
    return {"acted": True, "coords": [cx, cy], "scrolls": found["scrolls"],
            "result": result}
