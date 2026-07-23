"""Hold modifier keys across a group of actions, releasing them safely.

``hotkey`` presses a set of keys and releases them immediately — fine for a
one-shot chord, but there is no way to hold ``ctrl`` (or ``shift``) *down across
several independent actions* (range-select with shift-clicks, ctrl-clicks to
multi-select) and be sure the modifiers are released even if one of those actions
raises.

:func:`plan_with_modifiers` wraps an op-step list with press / release steps and
is pure / unit-testable; :func:`hold_modifiers` is a context manager that presses
on enter and releases (in reverse) on exit — including on exception — dispatching
through an injectable ``sink``. Imports no ``PySide6``.
"""
import contextlib
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

Sink = Callable[[Dict[str, Any]], None]


def plan_with_modifiers(steps: Sequence[Dict[str, Any]],
                        modifiers: Sequence[str]) -> List[Dict[str, Any]]:
    """Wrap ``steps`` with press-modifiers (in order) … release-modifiers (reversed)."""
    mods = list(modifiers)
    plan: List[Dict[str, Any]] = [{"op": "press", "key": mod} for mod in mods]
    plan.extend(dict(step) for step in steps)
    plan.extend({"op": "release", "key": mod} for mod in reversed(mods))
    return plan


def _default_sink(event: Dict[str, Any]) -> None:
    """Default dispatch: drive the real keyboard backend."""
    from je_auto_control.wrapper.auto_control_keyboard import (
        press_keyboard_key, release_keyboard_key)
    if event["op"] == "press":
        press_keyboard_key(event["key"])
    elif event["op"] == "release":
        release_keyboard_key(event["key"])


@contextlib.contextmanager
def hold_modifiers(modifiers: Sequence[str], *,
                   sink: Optional[Sink] = None) -> Iterator[List[str]]:
    """Hold ``modifiers`` down for the ``with`` block; release them on exit.

    Modifiers are pressed in order on entry and released in reverse order on
    exit — even if the body raises — so a stuck modifier can never leak. Dispatch
    goes through ``sink`` (default: the real keyboard backend).
    """
    dispatch = sink or _default_sink
    mods = list(modifiers)
    pressed: List[str] = []
    try:
        # Presses live inside the try so a failure part-way through still
        # releases whatever was already pressed. ``pressed`` records the ones
        # that actually went down, so a mid-press exception can never leak a
        # held modifier.
        for mod in mods:
            dispatch({"op": "press", "key": mod})
            pressed.append(mod)
        yield mods
    finally:
        for mod in reversed(pressed):
            try:
                dispatch({"op": "release", "key": mod})
            except Exception:  # noqa: BLE001  # reason: best-effort release — one failing release must not skip the rest or mask the body error
                autocontrol_logger.exception(
                    "hold_modifiers release failed for %r", mod,
                )
