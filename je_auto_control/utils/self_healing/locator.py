"""Self-healing locator: image template first, VLM fallback on miss.

Wraps the existing :func:`locate_image_center` and
:func:`locate_by_description` calls in a single API that:

* runs the cheap template-match path first;
* on miss, asks a vision-language model to find the element by
  natural-language description;
* records every attempt (hit / heal / miss) to a JSON-lines log so
  flaky locators can be audited and tuned over time;
* never raises on a miss by default — returns a :class:`HealOutcome`
  the caller can branch on.

The wrapper is platform-agnostic and Qt-free; the GUI panel and MCP
tool are thin shells over it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.self_healing.heal_log import (
    HealEvent, HealEventLog, default_heal_log,
)


METHOD_IMAGE = "image"
METHOD_VLM = "vlm"
METHOD_MISS = "miss"


class SelfHealError(RuntimeError):
    """Raised by self-heal calls when ``raise_on_miss=True`` and both
    locator strategies (template match and VLM) come up empty.
    """


@dataclass(frozen=True)
class HealOutcome:
    """Result of a single self-heal attempt."""

    found: bool
    coordinates: Optional[Tuple[int, int]]
    method: str
    description: Optional[str] = None
    template_path: Optional[str] = None
    image_error: Optional[str] = None
    vlm_error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict (tuple → list) for executor / MCP responses."""
        data = asdict(self)
        if self.coordinates is not None:
            data["coordinates"] = [int(self.coordinates[0]),
                                   int(self.coordinates[1])]
        return data


def self_heal_locate(template_path: Optional[str] = None,
                     description: Optional[str] = None,
                     detect_threshold: float = 0.9,
                     screen_region: Optional[List[int]] = None,
                     model: Optional[str] = None,
                     log: Optional[HealEventLog] = None,
                     raise_on_miss: bool = False,
                     ) -> HealOutcome:
    """Locate an element by template; fall back to VLM on miss.

    At least one of ``template_path`` / ``description`` must be given.
    Provide both for full self-healing — the VLM path only runs when
    the template match fails or returns no candidates.
    """
    if not template_path and not description:
        raise ValueError(
            "self_heal_locate requires template_path or description",
        )
    started = monotonic()
    coords, image_error = _try_image(template_path, detect_threshold)
    if coords is not None:
        return _finish(
            HealOutcome(found=True, coordinates=coords, method=METHOD_IMAGE,
                        description=description, template_path=template_path,
                        duration_ms=_ms_since(started)),
            log,
        )
    coords, vlm_error = _try_vlm(description, screen_region, model)
    if coords is not None:
        autocontrol_logger.warning(
            f"self_heal: image miss ({image_error}); VLM healed → {coords}",
        )
        return _finish(
            HealOutcome(found=True, coordinates=coords, method=METHOD_VLM,
                        description=description, template_path=template_path,
                        image_error=image_error,
                        duration_ms=_ms_since(started)),
            log,
        )
    outcome = HealOutcome(
        found=False, coordinates=None, method=METHOD_MISS,
        description=description, template_path=template_path,
        image_error=image_error, vlm_error=vlm_error,
        duration_ms=_ms_since(started),
    )
    _finish(outcome, log)
    if raise_on_miss:
        raise SelfHealError(
            f"self_heal_locate failed: image={image_error!r} vlm={vlm_error!r}",
        )
    return outcome


def self_heal_click(template_path: Optional[str] = None,
                    description: Optional[str] = None,
                    mouse_keycode: str = "mouse_left",
                    detect_threshold: float = 0.9,
                    screen_region: Optional[List[int]] = None,
                    model: Optional[str] = None,
                    log: Optional[HealEventLog] = None,
                    raise_on_miss: bool = False,
                    ) -> HealOutcome:
    """``self_heal_locate`` + a click at the resolved coordinates."""
    outcome = self_heal_locate(
        template_path=template_path, description=description,
        detect_threshold=detect_threshold, screen_region=screen_region,
        model=model, log=log, raise_on_miss=raise_on_miss,
    )
    if outcome.found and outcome.coordinates is not None:
        _click_at(outcome.coordinates, mouse_keycode)
    return outcome


def _try_image(template_path: Optional[str],
               detect_threshold: float,
               ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if not template_path:
        return None, "no template_path supplied"
    try:
        from je_auto_control.wrapper.auto_control_image import (
            locate_image_center,
        )
        cx, cy = locate_image_center(
            template_path, detect_threshold=float(detect_threshold),
        )
        return (int(cx), int(cy)), None
    except ImageNotFoundException as exc:
        return None, str(exc)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        return None, repr(exc)


def _try_vlm(description: Optional[str],
             screen_region: Optional[List[int]],
             model: Optional[str],
             ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if not description:
        return None, "no description supplied"
    try:
        from je_auto_control.utils.vision.vlm_api import locate_by_description
        coords = locate_by_description(
            description, screen_region=screen_region, model=model,
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        return None, repr(exc)
    if coords is None:
        return None, "vlm returned no match"
    return (int(coords[0]), int(coords[1])), None


def _click_at(coordinates: Tuple[int, int], mouse_keycode: str) -> None:
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position,
    )
    cx, cy = int(coordinates[0]), int(coordinates[1])
    set_mouse_position(cx, cy)
    click_mouse(mouse_keycode, cx, cy)


def _ms_since(started: float) -> float:
    return round((monotonic() - started) * 1000.0, 2)


def _finish(outcome: HealOutcome,
            log: Optional[HealEventLog]) -> HealOutcome:
    target = log if log is not None else default_heal_log
    try:
        target.append(_as_event(outcome))
    except (OSError, ValueError) as exc:
        autocontrol_logger.warning(f"self_heal log append failed: {exc!r}")
    return outcome


def _as_event(outcome: HealOutcome) -> HealEvent:
    coords = (
        [int(outcome.coordinates[0]), int(outcome.coordinates[1])]
        if outcome.coordinates is not None else None
    )
    return HealEvent(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        method=outcome.method,
        coordinates=coords,
        duration_ms=outcome.duration_ms,
        template_path=outcome.template_path,
        description=outcome.description,
        image_error=outcome.image_error,
        vlm_error=outcome.vlm_error,
    )


__all__ = [
    "HealOutcome", "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM",
    "SelfHealError", "self_heal_click", "self_heal_locate",
]
