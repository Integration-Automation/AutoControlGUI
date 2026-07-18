"""Hold a key for a duration, or auto-repeat it at a fixed rate.

``type_keyboard`` is an instant down+up and ``input_macro.run_sequence`` can hand-
roll a press / wait / release, but there is no primitive for "hold this key for N
seconds" (game movement, hold-to-scroll) or "send it at R presses per second"
(auto-repeat). :func:`plan_key_hold` builds the deterministic op-plan (pure,
unit-testable); :func:`hold_key` dispatches it through an injectable ``sink`` and
``sleep`` so it is tested without real input or real waiting. Imports no
``PySide6``.
"""
import time
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

Sink = Callable[[Dict[str, Any]], None]


def plan_key_hold(key: str, duration_s: float, *,
                  rate_hz: Optional[float] = None) -> List[Dict[str, Any]]:
    """Return the op-plan to hold (or auto-repeat) ``key`` for ``duration_s``.

    With ``rate_hz`` unset the key is pressed, held for ``duration_s``, then
    released. With ``rate_hz`` set it is sent as ``round(duration_s * rate_hz)``
    discrete key events spaced ``1 / rate_hz`` apart (simulated auto-repeat).
    Raises ``ValueError`` on a non-positive duration or rate.
    """
    if duration_s <= 0:
        raise ValueError("duration_s must be positive")
    if rate_hz is None:
        return [{"op": "press", "key": key},
                {"op": "wait", "seconds": float(duration_s)},
                {"op": "release", "key": key}]
    if rate_hz <= 0:
        raise ValueError("rate_hz must be positive")
    interval = 1.0 / float(rate_hz)
    count = max(1, round(float(duration_s) * float(rate_hz)))
    plan: List[Dict[str, Any]] = []
    for index in range(count):
        plan.append({"op": "key", "key": key})
        if index != count - 1:
            plan.append({"op": "wait", "seconds": interval})
    return plan


def _default_sink(event: Dict[str, Any]) -> None:
    """Default dispatch: drive the real keyboard backend."""
    from je_auto_control.wrapper.auto_control_keyboard import (
        press_keyboard_key, release_keyboard_key, type_keyboard)
    op = event["op"]
    if op == "press":
        press_keyboard_key(event["key"])
    elif op == "release":
        release_keyboard_key(event["key"])
    elif op == "key":
        type_keyboard(event["key"])


def _dispatch_tracking_holds(dispatch: Sink, event: Dict[str, Any],
                             held: List[str]) -> None:
    """Dispatch one non-wait op, keeping ``held`` in sync with press/release."""
    dispatch(event)
    op = event["op"]
    if op == "press":
        held.append(event["key"])
    elif op == "release" and event["key"] in held:
        held.remove(event["key"])


def _release_held(dispatch: Sink, held: List[str]) -> None:
    """Best-effort release of any keys still down (e.g. after an interrupt)."""
    for held_key in held:
        try:
            dispatch({"op": "release", "key": held_key})
        except Exception:  # noqa: BLE001  # reason: best-effort teardown release — a stuck key is worse than a swallowed error
            autocontrol_logger.exception(
                "hold_key release failed for %r", held_key,
            )


def hold_key(key: str, duration_s: float, *, rate_hz: Optional[float] = None,
             sink: Optional[Sink] = None,
             sleep: Optional[Callable[[float], None]] = None) -> Dict[str, Any]:
    """Hold or auto-repeat ``key`` for ``duration_s``; return the dispatched plan.

    ``wait`` ops go to ``sleep`` (default :func:`time.sleep`); key ops go to
    ``sink`` (default: the real keyboard backend). A KeyboardInterrupt during
    the hold wait, or a failing release, still releases the key via the finally
    block (auto-repeat plans only ``type`` keys, so nothing is held there).
    """
    plan = plan_key_hold(key, duration_s, rate_hz=rate_hz)
    dispatch = sink or _default_sink
    pause = sleep or time.sleep
    held: List[str] = []
    try:
        for event in plan:
            if event["op"] == "wait":
                pause(event["seconds"])
            else:
                _dispatch_tracking_holds(dispatch, event, held)
    finally:
        _release_held(dispatch, held)
    return {"ops": len(plan), "plan": plan}
