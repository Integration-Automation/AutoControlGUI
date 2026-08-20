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
import time
from typing import Any, Callable, Dict, List, Optional


def _sink_move(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
    set_mouse_position(int(event.get("x", 0)), int(event.get("y", 0)))


def _sink_click(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position)
    x, y = int(event.get("x", 0)), int(event.get("y", 0))
    set_mouse_position(x, y)
    click_mouse(event.get("button", "mouse_left"), x, y)


def _sink_scroll(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import mouse_scroll
    # ``value`` is the DSL's name for it, ``delta`` the recorder's. The sign
    # is kept: it is what decides the direction on Windows and macOS. Linux
    # takes its direction from `scroll_direction` instead, which is an open
    # cross-platform decision recorded in Progress.md, not something to
    # settle here.
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
_RECORDED_BUTTON = {"left": "mouse_left", "right": "mouse_right",
                    "middle": "mouse_middle"}


def _sink_key_down(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key
    press_keyboard_key(event["vk"])


def _sink_key_up(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_keyboard import (
        release_keyboard_key)
    release_keyboard_key(event["vk"])


def _sink_mouse_down(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import press_mouse
    press_mouse(_RECORDED_BUTTON.get(event.get("button", ""), "mouse_left"),
                int(event.get("x", 0)), int(event.get("y", 0)))


def _sink_mouse_up(event: Dict[str, Any]) -> None:
    from je_auto_control.wrapper.auto_control_mouse import release_mouse
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
    if handler is not None:
        handler(event)


def replay_timeline(events: List[Dict[str, Any]], *, speed: float = 1.0,
                    sink: Optional[Callable] = None,
                    sleep: Optional[Callable] = None,
                    min_gap: float = 0.0,
                    max_gap: Optional[float] = None) -> int:
    """Replay ``events`` honoring per-event ``delta_ms`` gaps; return count.

    ``speed`` > 1 plays faster (gaps divided by speed). Gaps are clamped to
    ``[min_gap, max_gap]``. Each event is dispatched via ``sink`` (default:
    real input); ``sleep`` is injectable for tests.
    """
    dispatch = sink or _default_sink
    sleeper = sleep or time.sleep
    factor = max(float(speed), 1e-9)
    played = 0
    for event in events:
        gap = float(event.get("delta_ms", 0)) / 1000.0 / factor
        gap = max(float(min_gap), gap)
        if max_gap is not None:
            gap = min(gap, float(max_gap))
        if gap > 0:
            sleeper(gap)
        dispatch(event)
        played += 1
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
    ``{op: wait, ms}`` and ``{op: repeat, times, steps:[...]}``.
    """
    dispatch = sink or _default_sink
    sleeper = sleep or time.sleep
    log: List[Dict[str, Any]] = []
    _run_steps(steps, dispatch, sleeper, log)
    return log
