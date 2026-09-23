"""Timed input-event replay and a declarative input-sequence DSL.

The recorder captures *what* happened but replays it without timing; this
adds fidelity:

* :func:`replay_timeline` plays a list of events honoring each event's
  ``delta_ms`` gap, scaled by a global ``speed`` (2x faster / 0.5x slower).
* :func:`run_sequence` runs a small declarative DSL — ``press`` / ``release``
  / ``key`` / ``click`` / ``move`` / ``scroll`` / ``wait`` / ``repeat`` —
  for press-hold-release chords and repeated input.

Both dispatch each event through an injectable ``sink`` and use an
injectable ``sleep``, so timing and sequencing are unit-tested
deterministically with a fake clock and a recording sink — no real input.
Imports no ``PySide6``.
"""
import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


def _sink_move(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
    set_mouse_position(int(event.get("x", 0)), int(event.get("y", 0)))


def _sink_click(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position)
    x, y = int(event.get("x", 0)), int(event.get("y", 0))
    set_mouse_position(x, y)
    click_mouse(event.get("button", "mouse_left"), x, y)


def _move_to_event(event: Dict[str, Any]) -> None:
    """Put the cursor where a recorded event happened (when it says where).

    The Windows and X11 backends press and scroll wherever the cursor is, so
    without this a recorded drag replayed as a click in place.
    """
    if "x" in event and "y" in event:
        _sink_move(event)


def _sink_scroll(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import mouse_scroll
    _move_to_event(event)
    # ``value`` is the DSL's name for it, ``delta`` the recorder's. The sign
    # is kept, and that is now enough: a negative value reverses the
    # direction on every backend, X11 and Wayland included. They used to
    # discard it and always scroll ``scroll_direction``, so a macro
    # recorded on Windows replayed backwards there, silently.
    mouse_scroll(int(event.get("value", event.get("delta", 1))))


def _sink_press(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key
    press_keyboard_key(event["key"])


def _sink_release(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import (
        release_keyboard_key)
    release_keyboard_key(event["key"])


def _sink_key(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
    type_keyboard(event["key"])


# The recorder names a button "left"; the input API names it "mouse_left".
#: Recorded button name -> mouse-table key. The lookups below fall back to
#: ``mouse_left``, so every name a recorder can emit MUST appear here: a missing
#: entry does not drop the event, it replays it as a LEFT click. That is why
#: ``x1`` / ``x2`` landed here in the same change that taught the Windows hook
#: to record ``WM_XBUTTON*`` -- adding one without the other is worse than the
#: gap it closes.
_RECORDED_BUTTON = {"left": "mouse_left", "right": "mouse_right",
                    "middle": "mouse_middle",
                    "x1": "mouse_x1", "x2": "mouse_x2"}


def _sink_key_down(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key
    press_keyboard_key(event["vk"])


def _sink_key_up(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import (
        release_keyboard_key)
    release_keyboard_key(event["vk"])


def _sink_mouse_down(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import press_mouse
    _move_to_event(event)
    press_mouse(_RECORDED_BUTTON.get(event.get("button", ""), "mouse_left"),
                int(event.get("x", 0)), int(event.get("y", 0)))


def _sink_mouse_up(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import release_mouse
    _move_to_event(event)
    release_mouse(_RECORDED_BUTTON.get(event.get("button", ""), "mouse_left"),
                  int(event.get("x", 0)), int(event.get("y", 0)))


#: Two vocabularies reach this table and both have to work. The `run_sequence`
#: DSL writes ``press`` / ``click`` / ``key``; the recorders write
#: ``key_down`` / ``mouse_up`` and so on. They used to be disjoint, so feeding
#: ``stop_record_timeline()`` to :func:`replay_timeline` — the pipeline the
#: docstrings and the ``ac_record_stop_timeline`` tool both prescribe —
#: matched nothing and replayed an empty session while reporting the full
#: event count as played.
_SINKS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    "move": _sink_move, "click": _sink_click, "scroll": _sink_scroll,
    "press": _sink_press, "release": _sink_release, "key": _sink_key,
    "key_down": _sink_key_down, "key_up": _sink_key_up,
    "mouse_down": _sink_mouse_down, "mouse_up": _sink_mouse_up,
}


def _default_sink(event: Dict[str, Any]) -> None:
    handler = _SINKS.get(event.get("op", ""))
    if handler is None:
        # A typo ("presss") used to be skipped while reported as played.
        raise ValueError(f"unknown input op {event.get('op')!r}")
    handler(event)


#: A "down" op -> (the op that releases it, the key identifying what is held).
_RELEASE_FOR = {"press": ("release", "key"), "key_down": ("key_up", "vk"),
                "mouse_down": ("mouse_up", "button")}


class _HeldInputs:
    """Tracks keys and buttons pressed and not yet released, to release on error.

    A step that failed between a press and its release left the key (Shift,
    a mouse button) held down after the call returned.
    """

    def __init__(self, dispatch: Callable) -> None:
        self._dispatch = dispatch
        self._held: List[Tuple[str, str, Any]] = []

    def __call__(self, event: Dict[str, Any]) -> None:
        self._dispatch(event)
        op = event.get("op")
        if op in _RELEASE_FOR:
            release_op, field = _RELEASE_FOR[op]
            self._held.append((release_op, field, event.get(field)))
            return
        for index, (release_op, field, value) in enumerate(self._held):
            if op == release_op and event.get(field) == value:
                del self._held[index]
                return

    def release_all(self) -> None:
        """Release everything still held, newest first; keep going on errors."""
        while self._held:
            release_op, field, value = self._held.pop()
            try:
                self._dispatch({"op": release_op, field: value})
            except Exception as error:  # noqa: BLE001  # reason: cleanup after a failure must try every held input; the original error is re-raised by the caller
                from je_auto_control.utils.logging.logging_instance import autocontrol_logger
                autocontrol_logger.warning("could not release %r: %r", value, error)


def _playback_factor(speed: float) -> float:
    factor = float(speed)
    if not math.isfinite(factor) or factor <= 0:
        # 0 or a negative speed slept ~3 years per gap; NaN dropped all timing.
        raise ValueError(f"speed must be a positive number, got {speed!r}")
    return factor


def replay_timeline(events: List[Dict[str, Any]], *, speed: float = 1.0,
                    sink: Optional[Callable] = None,
                    sleep: Optional[Callable] = None,
                    min_gap: float = 0.0,
                    max_gap: Optional[float] = None) -> int:
    """Replay ``events`` honoring per-event ``delta_ms`` gaps; return count.

    ``speed`` > 1 plays faster (gaps divided by speed) and must be a positive
    number. Gaps are clamped to ``[min_gap, max_gap]``. Each event is
    dispatched via ``sink`` (default: real input, at the event's recorded
    position; an unknown op raises); ``sleep`` is injectable for tests. If an
    event fails, keys and buttons still held are released before the error
    propagates.
    """
    dispatch = _HeldInputs(sink or _default_sink)
    sleeper = sleep or time.sleep
    factor = _playback_factor(speed)
    played = 0
    try:
        for event in events:
            gap = float(event.get("delta_ms", 0)) / 1000.0 / factor
            gap = max(float(min_gap), gap)
            if max_gap is not None:
                gap = min(gap, float(max_gap))
            if gap > 0:
                sleeper(gap)
            dispatch(event)
            played += 1
    except BaseException:
        dispatch.release_all()
        raise
    return played


def _run_steps(steps: List[Dict[str, Any]], dispatch: Callable,
               sleeper: Callable, log: List[Dict[str, Any]]) -> None:
    for step in steps:
        op = step.get("op")
        if op == "repeat":
            for _ in range(int(step.get("times", 1))):
                _run_steps(step.get("steps", []), dispatch, sleeper, log)
        elif op == "wait":
            sleeper(float(step.get("ms", 0)) / 1000.0)
            log.append({"op": "wait", "ms": step.get("ms", 0)})
        else:
            dispatch(step)
            log.append(dict(step))


def run_sequence(steps: List[Dict[str, Any]], *,
                 sink: Optional[Callable] = None,
                 sleep: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Run a declarative input sequence; return the flattened executed log.

    Steps are ``{op: press|release|key|click|move|scroll}`` plus control ops
    ``{op: wait, ms}`` and ``{op: repeat, times, steps:[...]}``. An unknown op
    raises, and keys still held when a step fails are released first.
    """
    dispatch = _HeldInputs(sink or _default_sink)
    sleeper = sleep or time.sleep
    log: List[Dict[str, Any]] = []
    try:
        _run_steps(steps, dispatch, sleeper, log)
    except BaseException:
        dispatch.release_all()
        raise
    return log
