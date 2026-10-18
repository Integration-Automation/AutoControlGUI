"""Self-healing locator: image template first, VLM fallback on miss.

Wraps the existing :func:`locate_image_center` and
:func:`locate_by_description` calls in a single API that:

* runs the cheap template-match path first;
* on miss, asks a vision-language model to find the element by
  natural-language description;
* reuses one lazy logical capture across both strategies;
* records every attempt (candidate / miss) to a JSON-lines log so
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
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, ImageNotFoundException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.cv2_utils.locator_frame import locator_frame_scope
from je_auto_control.utils.self_healing.runtime_evidence import AttemptEvidence, attempt_evidence
from je_auto_control.utils.self_healing.heal_log import (
    HealEvent, HealEventLog, default_heal_log,
)


METHOD_IMAGE = "image"
METHOD_VLM = "vlm"
METHOD_MISS = "miss"
_Result = TypeVar("_Result")


class SelfHealError(AutoControlException, RuntimeError):
    """Raised by self-heal calls when ``raise_on_miss=True`` and both
    locator strategies (template match and VLM) come up empty.
    """


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: preserve the existing eight-field public result
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


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable request values preserve both legacy call signatures
class _LocateCall:
    template_path: Optional[str]
    description: Optional[str]
    detect_threshold: float
    screen_region: Optional[List[int]]
    model: Optional[str]
    log: Optional[HealEventLog]
    raise_on_miss: bool
    mouse_keycode: Optional[str] = None


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
    Cancellation propagates unchanged without fallback, click or miss logging.
    ``screen_region`` is a logical [left, top, right, bottom] bbox for both
    strategies, clipped to the desktop. With a template, an omitted region
    searches the virtual desktop; VLM-only calls retain the primary request.
    Backend-reported nonzero origins are honored even for primary requests.
    """
    return _run(_LocateCall(template_path, description, detect_threshold, screen_region, model, log, raise_on_miss))


def _run(call: _LocateCall) -> HealOutcome:
    if not call.template_path and not call.description:
        raise ValueError(
            "self_heal_locate requires template_path or description",
        )
    started = monotonic()
    with locator_frame_scope(call.screen_region, all_screens=bool(call.template_path)) as source:
        evidence = attempt_evidence(source, call.template_path, call.description, call.detect_threshold, call.model)
        outcome = _locate(call, evidence, started)
        if call.mouse_keycode is not None:
            _click(outcome, call, evidence)
        _finish(outcome, call.log, evidence.fields())
    if not outcome.found and call.raise_on_miss:
        raise SelfHealError(f"self_heal_locate failed: image={outcome.image_error!r} vlm={outcome.vlm_error!r}")
    return outcome


def _timed(name: str, operation: Callable[[], _Result], evidence: AttemptEvidence) -> _Result:
    started = monotonic()
    try:
        return operation()
    finally:
        evidence.strategy_times_ms[name] = (monotonic() - started) * 1000


def _locate(call: _LocateCall, evidence: AttemptEvidence, started: float) -> HealOutcome:
    template_path, description = call.template_path, call.description
    def image() -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
        return _try_image(template_path, call.detect_threshold)
    coords, image_error = _timed("image", image, evidence) if template_path else image()
    if coords is not None:
        return HealOutcome(found=True, coordinates=coords, method=METHOD_IMAGE,
                        description=description, template_path=template_path,
                        duration_ms=_ms_since(started))
    def vlm() -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
        return _try_vlm(description, call.screen_region, call.model)
    coords, vlm_error = _timed("vlm", vlm, evidence) if description else vlm()
    if coords is not None:
        autocontrol_logger.warning(
            "self_heal: image miss (%s); VLM located unverified candidate at %s", image_error, coords,
        )
        return HealOutcome(found=True, coordinates=coords, method=METHOD_VLM,
                        description=description, template_path=template_path,
                        image_error=image_error,
                        duration_ms=_ms_since(started))
    return HealOutcome(
        found=False, coordinates=None, method=METHOD_MISS,
        description=description, template_path=template_path,
        image_error=image_error, vlm_error=vlm_error,
        duration_ms=_ms_since(started),
    )


# pylint: disable-next=too-many-arguments,too-many-positional-arguments  # reason: preserve the existing public signature
def self_heal_click(template_path: Optional[str] = None,
                    description: Optional[str] = None,
                    mouse_keycode: str = "mouse_left",
                    detect_threshold: float = 0.9,
                    screen_region: Optional[List[int]] = None,
                    model: Optional[str] = None,
                    log: Optional[HealEventLog] = None,
                    raise_on_miss: bool = False,
                    ) -> HealOutcome:
    """Locate and issue a click; this does not verify the resulting UI state.

    One audit record is settled after dispatch. An ordinary click failure is
    recorded and re-raised unchanged; cancellation emits no completion event.
    The historical eight-field result and locate-duration semantics are kept.
    """
    if not isinstance(mouse_keycode, str) or not mouse_keycode:
        raise ValueError("mouse_keycode must be a nonempty string")
    return _run(_LocateCall(template_path, description, detect_threshold, screen_region,
                            model, log, raise_on_miss, mouse_keycode))


def _click(outcome: HealOutcome, call: _LocateCall, evidence: AttemptEvidence) -> None:
    evidence.operation, evidence.operation_status = "click", "not_found"
    coordinates, keycode = outcome.coordinates, call.mouse_keycode
    if not outcome.found or coordinates is None or keycode is None:
        return
    try:
        _timed("click", lambda: _click_at(coordinates, keycode), evidence)
        evidence.operation_status = "issued"
    except Exception as error:  # reason: record an ordinary click error once, then preserve the original exception
        # pylint: disable-next=import-outside-toplevel  # reason: run outcomes import the executor during facade setup
        from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text, raise_if_run_interrupted
        raise_if_run_interrupted(error)
        evidence.operation_status, evidence.operation_error = "error", _ordinary_error_text(error)
        try:
            _finish(outcome, call.log, evidence.fields())
        # pylint: disable-next=broad-exception-caught  # reason: preserve the pending original failure across audit plugins
        except Exception:  # reason: telemetry failure cannot replace the original click failure
            autocontrol_logger.error("self_heal audit unavailable; preserving original click failure")
        raise


def _try_image(template_path: Optional[str],
               detect_threshold: float,
               ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if not template_path:
        return None, "no template_path supplied"
    try:
        # pylint: disable-next=import-outside-toplevel  # reason: platform image support remains lazy during facade setup
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
        return None, _failure_detail(exc)


def _try_vlm(description: Optional[str],
             screen_region: Optional[List[int]],
             model: Optional[str],
             ) -> Tuple[Optional[Tuple[int, int]], Optional[str]]:
    if not description:
        return None, "no description supplied"
    try:
        # pylint: disable-next=import-outside-toplevel  # reason: backend selection is deferred until VLM is attempted
        from je_auto_control.utils.vision.vlm_api import locate_by_description
        coords = locate_by_description(
            description, screen_region=screen_region, model=model,
        )
    # AutoControlException: a failed screenshot (AutoControlScreenException)
    # escaped the self-heal and left no heal-log entry.
    except (AutoControlException, OSError, RuntimeError, ValueError, TypeError) as exc:
        return None, _failure_detail(exc)
    if coords is None:
        return None, "vlm returned no match"
    return (int(coords[0]), int(coords[1])), None


def _failure_detail(error: Exception) -> str:
    """Propagate cancellation before formatting an ordinary locator failure."""
    # pylint: disable-next=import-outside-toplevel  # reason: run outcomes import the executor during facade setup
    from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text, raise_if_run_interrupted
    raise_if_run_interrupted(error)
    return _ordinary_error_text(error)


def _click_at(coordinates: Tuple[int, int], mouse_keycode: str) -> None:
    # pylint: disable-next=import-outside-toplevel  # reason: platform input initializes only when a click is requested
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position,
    )
    cx, cy = int(coordinates[0]), int(coordinates[1])
    set_mouse_position(cx, cy)
    click_mouse(mouse_keycode, cx, cy)


def _ms_since(started: float) -> float:
    return round((monotonic() - started) * 1000.0, 2)


def _finish(outcome: HealOutcome,
            log: Optional[HealEventLog], metadata: Optional[Dict[str, Any]] = None) -> HealOutcome:
    target = log if log is not None else default_heal_log
    try:
        target.append(_as_event(outcome, metadata))
    except (OSError, ValueError) as exc:
        autocontrol_logger.warning("self_heal log append failed: %r", exc)
    return outcome


def _as_event(outcome: HealOutcome, metadata: Optional[Dict[str, Any]] = None) -> HealEvent:
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
        **(metadata or {}),
    )


__all__ = [
    "HealOutcome", "METHOD_IMAGE", "METHOD_MISS", "METHOD_VLM",
    "SelfHealError", "self_heal_click", "self_heal_locate",
]
