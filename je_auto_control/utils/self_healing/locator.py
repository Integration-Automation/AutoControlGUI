"""Self-healing locator: image template first, VLM fallback on miss.

Wraps the existing :func:`locate_image_center` and
:func:`locate_by_description` calls in a single API that:

* runs the cheap template-match path first;
* on miss, asks a vision-language model to find the element by
  natural-language description;
* records every attempt (hit / heal / miss) to a JSON-lines log so
  flaky locators can be audited and tuned over time;
* never raises on a miss by default — returns a :class:`HealOutcome`
  the caller can branch on;
* keeps "the locator found something" (``found``) apart from "the action
  that followed was checked" (``action_verified``): a VLM that answers with
  a confident wrong point is a hit by the first measure and nothing by the
  second, and counting it as a recovery is how a healing rate lies.

``screen_region`` is ``[x1, y1, x2, y2]`` in screen coordinates and confines
**both** strategies. It used to reach only the VLM, so a template match could
"find" the element outside the region the caller asked to search.

The wrapper is platform-agnostic and Qt-free; the GUI panel and MCP
tool are thin shells over it.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from time import monotonic
from typing import (
    Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple,
)

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, ImageNotFoundException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.self_healing.heal_log import (
    HEAL_EVENT_SCHEMA_VERSION, HealEvent, HealEventLog, default_heal_log,
)
from je_auto_control.utils.thread_bound import ThreadBoundVar


METHOD_IMAGE = "image"
METHOD_VLM = "vlm"
METHOD_MISS = "miss"
ACTION_CLICK = "click"

#: Keys :func:`heal_context` accepts; each is a string column of the heal log.
CONTEXT_KEYS = ("run_id", "step_id", "locator_id", "locator_version", "backend")

# Thread-bound: where a new thread inherits its creator's context variables (a
# free-threaded build), a thread started inside a heal_context block would
# otherwise stamp its own, unrelated heal events with that run and step.
_NO_CONTEXT: Mapping[str, str] = {}
_context: ThreadBoundVar[Mapping[str, str]] = ThreadBoundVar("self_heal_context", _NO_CONTEXT)


@contextmanager
def heal_context(**values: Optional[str]) -> Iterator[None]:
    """Stamp every heal event logged inside the block with ``values``.

    Accepts the :data:`CONTEXT_KEYS` (``run_id``, ``step_id``, ``locator_id``,
    ``locator_version``, ``backend``); ``None`` values are ignored and an
    unknown key raises ``ValueError``. Nested blocks layer over outer ones.
    The stamp applies on the calling thread only, on every build.
    """
    unknown = sorted(set(values) - set(CONTEXT_KEYS))
    if unknown:
        raise ValueError(f"unknown heal context key(s) {unknown}; expected {list(CONTEXT_KEYS)}")
    merged = dict(_context.get())
    merged.update({key: str(value) for key, value in values.items() if value is not None})
    token = _context.set(merged)
    try:
        yield
    finally:
        _context.reset(token)


class SelfHealError(AutoControlException, RuntimeError):
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
    screen_region: Optional[Tuple[int, int, int, int]] = None
    model: Optional[str] = None
    image_ms: Optional[float] = None
    vlm_ms: Optional[float] = None
    #: ``"click"`` once the hit was acted on; ``None`` for a bare locate.
    action: Optional[str] = None
    #: Result of the caller's post-action check; ``None`` when none ran.
    action_verified: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict (tuple → list) for executor / MCP responses."""
        data = asdict(self)
        if self.coordinates is not None:
            data["coordinates"] = [int(self.coordinates[0]),
                                   int(self.coordinates[1])]
        if self.screen_region is not None:
            data["screen_region"] = [int(value) for value in self.screen_region]
        return data


def self_heal_locate(template_path: Optional[str] = None,
                     description: Optional[str] = None,
                     detect_threshold: float = 0.9,
                     screen_region: Optional[List[int]] = None,
                     model: Optional[str] = None,
                     log: Optional[HealEventLog] = None,
                     raise_on_miss: bool = False,
                     frame: Optional[Any] = None,
                     ) -> HealOutcome:
    """Locate an element by template; fall back to VLM on miss.

    At least one of ``template_path`` / ``description`` must be given.
    Provide both for full self-healing — the VLM path only runs when
    the template match fails or returns no candidates. ``screen_region``
    (``[x1, y1, x2, y2]``, screen coordinates) confines both strategies.

    ``frame`` (a ``DeviceFrame`` from ``DeviceSession.capture()``) is searched
    instead of the desktop; the coordinates are then device points.
    """
    outcome = _locate(template_path, description, detect_threshold,
                      _checked_region(screen_region), model, frame)
    _finish(outcome, log)
    _raise_on_miss(outcome, raise_on_miss)
    return outcome


def self_heal_click(template_path: Optional[str] = None,
                    description: Optional[str] = None,
                    mouse_keycode: str = "mouse_left",
                    detect_threshold: float = 0.9,
                    screen_region: Optional[List[int]] = None,
                    model: Optional[str] = None,
                    log: Optional[HealEventLog] = None,
                    raise_on_miss: bool = False,
                    verify: Callable[[HealOutcome], bool] | Mapping[str, Any] | None = None,
                    ) -> HealOutcome:
    """``self_heal_locate`` + a click at the resolved coordinates.

    ``verify`` is the post-click check whose truth value is recorded as
    ``action_verified``; without it the field stays ``None``. It is a callable
    taking the outcome, or -- what a JSON step can write -- an object such as
    ``{"type": "image_gone"}``, ``{"type": "image_present", "template_path":
    ...}`` or ``{"type": "text_present", "text": ...}`` (see
    :mod:`~je_auto_control.utils.self_healing.verification`). An object is
    validated before anything is clicked; a check that cannot be carried out
    raises and leaves ``action_verified`` ``None``. ``found`` only ever says
    that a strategy returned a point.
    """
    region = _checked_region(screen_region)
    if isinstance(verify, Mapping):
        from je_auto_control.utils.self_healing.verification import build_verifier
        verify = build_verifier(verify, template_path=template_path, screen_region=region)
    outcome = _locate(template_path, description, detect_threshold, region, model)
    if not outcome.found or outcome.coordinates is None:
        _finish(outcome, log)
        _raise_on_miss(outcome, raise_on_miss)
        return outcome
    target = outcome.coordinates
    outcome = replace(outcome, action=ACTION_CLICK)
    try:
        _click_at(target, mouse_keycode)
        if verify is not None:
            outcome = replace(outcome, action_verified=bool(verify(outcome)))
    finally:
        # Logged whether or not the click or the check raised: the attempt
        # happened, and an unverified one must not read as a verified one.
        _finish(outcome, log)
    return outcome


def _locate(template_path: Optional[str], description: Optional[str],
            detect_threshold: float, region: Optional[Tuple[int, int, int, int]],
            model: Optional[str], frame: Optional[Any] = None) -> HealOutcome:
    """Run image then VLM once; never logs, never raises on a miss."""
    if not template_path and not description:
        raise ValueError(
            "self_heal_locate requires template_path or description",
        )
    started = monotonic()
    base = HealOutcome(found=False, coordinates=None, method=METHOD_MISS,
                       description=description, template_path=template_path,
                       screen_region=region, model=model)
    # Without a frame the strategies are called exactly as before: callers
    # and tests replace them with two- and three-argument stand-ins.
    if frame is None:
        coords, image_error = _try_image_in_region(template_path, detect_threshold, region)
    else:
        coords, image_error = _try_image(template_path, detect_threshold, frame)
    image_ms = _ms_since(started)
    if coords is not None:
        return replace(base, found=True, coordinates=coords, method=METHOD_IMAGE,
                       image_ms=image_ms, duration_ms=_ms_since(started))
    vlm_started = monotonic()
    vlm_region = None if region is None else list(region)
    coords, vlm_error = (_try_vlm(description, vlm_region, model) if frame is None
                         else _try_vlm(description, vlm_region, model, frame))
    timed = replace(base, image_error=image_error, image_ms=image_ms,
                    vlm_ms=_ms_since(vlm_started) if description else None)
    if coords is not None:
        autocontrol_logger.warning(
            f"self_heal: image miss ({image_error}); VLM healed → {coords}",
        )
        return replace(timed, found=True, coordinates=coords, method=METHOD_VLM,
                       duration_ms=_ms_since(started))
    return replace(timed, vlm_error=vlm_error, duration_ms=_ms_since(started))


def _raise_on_miss(outcome: HealOutcome, raise_on_miss: bool) -> None:
    if raise_on_miss and not outcome.found:
        raise SelfHealError(
            f"self_heal_locate failed: image={outcome.image_error!r} vlm={outcome.vlm_error!r}",
        )


def _checked_region(screen_region: Optional[Sequence[int]],
                    ) -> Optional[Tuple[int, int, int, int]]:
    """``[x1, y1, x2, y2]`` as four ints with a positive area, or ``None``."""
    if screen_region is None:
        return None
    try:
        x1, y1, x2, y2 = (int(value) for value in screen_region)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"screen_region must be [x1, y1, x2, y2]; got {screen_region!r}") from error
    if x2 <= x1 or y2 <= y1:
        raise ValueError(
            f"screen_region must have x2 > x1 and y2 > y1; got {screen_region!r}")
    return x1, y1, x2, y2


def _try_image_in_region(template_path: Optional[str], detect_threshold: float,
                         region: Optional[Tuple[int, int, int, int]],
                         ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    """Template match confined to ``region``; the whole screen when it is ``None``."""
    if region is None or not template_path:
        return _try_image(template_path, detect_threshold)
    x1, y1, x2, y2 = region
    try:
        from je_auto_control.utils.cv2_utils import template_detection
        # The matcher takes (x, y, width, height); the heal API, like the VLM
        # path, takes two corners.
        result = template_detection.find_image(
            template_path, float(detect_threshold),
            screen_region=(x1, y1, x2 - x1, y2 - y1))
    except ImageNotFoundException as exc:
        return None, str(exc)
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as exc:
        return None, repr(exc)
    if not result[0]:
        return None, f"template not found in region {list(region)}"
    left, top, right, bottom = result[1]
    return (int((left + right) // 2), int((top + bottom) // 2)), None


def _try_image(template_path: Optional[str],
               detect_threshold: float,
               frame: Optional[Any] = None,
               ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if not template_path:
        return None, "no template_path supplied"
    try:
        if frame is not None:
            cx, cy = frame.locate_image(template_path, float(detect_threshold))
            return (int(cx), int(cy)), None
        from je_auto_control.wrapper.auto_control_image import (
            locate_image_center,
        )
        cx, cy = locate_image_center(
            template_path, detect_threshold=float(detect_threshold),
        )
        return (int(cx), int(cy)), None
    except ImageNotFoundException as exc:
        return None, str(exc)
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as exc:
        return None, repr(exc)


def _try_vlm(description: Optional[str],
             screen_region: Optional[List[int]],
             model: Optional[str],
             frame: Optional[Any] = None,
             ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if not description:
        return None, "no description supplied"
    try:
        from je_auto_control.utils.vision.vlm_api import locate_by_description
        coords = (frame.locate_description(description, model=model) if frame is not None
                  else locate_by_description(
                      description, screen_region=screen_region, model=model))
    # AutoControlException: a failed screenshot (AutoControlScreenException)
    # escaped the self-heal and left no heal-log entry.
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as exc:
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
    context = _context.get()
    return HealEvent(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        method=outcome.method,
        coordinates=coords,
        duration_ms=outcome.duration_ms,
        template_path=outcome.template_path,
        description=outcome.description,
        image_error=outcome.image_error,
        vlm_error=outcome.vlm_error,
        schema_version=HEAL_EVENT_SCHEMA_VERSION,
        run_id=context.get("run_id"),
        step_id=context.get("step_id"),
        locator_id=context.get("locator_id"),
        locator_version=context.get("locator_version"),
        backend=context.get("backend"),
        model=outcome.model,
        screen_region=(None if outcome.screen_region is None
                       else [int(value) for value in outcome.screen_region]),
        image_ms=outcome.image_ms,
        vlm_ms=outcome.vlm_ms,
        action=outcome.action,
        action_verified=outcome.action_verified,
    )


__all__ = [
    "ACTION_CLICK", "CONTEXT_KEYS", "HealOutcome",
    "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM",
    "SelfHealError", "heal_context", "self_heal_click", "self_heal_locate",
]
