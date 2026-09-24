"""Declarative finite-state-machine engine for action JSON."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException


# AutoControlException so `except AutoControlException` boundaries catch a
# stuck machine; RuntimeError kept for callers that caught that.
class StateMachineError(AutoControlException, RuntimeError):
    """Raised when the FSM spec is invalid or the run can't make progress."""


_DEFAULT_MAX_STEPS = 100
_DEFAULT_GLOBAL_TIMEOUT_S = 300.0


class StateMachine:
    """Run a state-machine spec against a pluggable action executor.

    ``execute_action`` is a single-action runner — typically a thin
    closure over :func:`je_auto_control.execute_action`. ``guard_eval``
    is a callable that decides whether a transition fires; it receives
    the transition dict, the FSM's mutable context and the monotonic time
    the current state was entered, and returns ``True`` to fire. The
    default guard evaluator understands ``after`` (seconds in the current
    state -- the machine waits for it), ``if_var_eq``, ``if_image_found``
    (a template path, or ``{"image": ..., "detect_threshold": ...}``) and
    ``predicate`` (a callable). Any other ``if_*`` key is an error rather
    than a guard that silently always passes.
    """

    def __init__(self, spec: Mapping[str, Any],
                 *, execute_action: Optional[Callable[[Any], Any]] = None,
                 guard_eval: Optional[Callable[..., bool]] = None) -> None:
        _validate_spec(spec)
        self._spec = dict(spec)
        self._states: Dict[str, Mapping[str, Any]] = dict(
            spec.get("states", {}),
        )
        self._execute = execute_action or _default_execute_action
        self._guard_eval = guard_eval or _default_guard_eval
        self._context: Dict[str, Any] = {}
        self._max_steps = int(spec.get("max_steps", _DEFAULT_MAX_STEPS))
        self._global_timeout_s = float(
            spec.get("global_timeout_s", _DEFAULT_GLOBAL_TIMEOUT_S),
        )

    @property
    def context(self) -> Dict[str, Any]:
        """Mutable scratch-pad shared across transitions / on_enter actions."""
        return self._context

    def run(self) -> Dict[str, Any]:
        """Drive the FSM to a final state or until budgets exhaust.

        Returns ``{"final_state": name, "steps": N, "elapsed_s": S}``.
        Raises :class:`StateMachineError` on budget exhaustion or when
        a state has no fireable transition.
        """
        current = self._spec["initial"]
        if current not in self._states:
            raise StateMachineError(f"initial state {current!r} undefined")
        started_at = time.monotonic()
        steps = 0
        while True:
            self._check_timeout(started_at, current)
            state = self._states[current]
            self._run_on_enter(state)
            # The final state is checked before the step budget: reaching
            # it on exactly the last allowed step is success, not exhaustion.
            if state.get("final"):
                return {
                    "final_state": current, "steps": steps,
                    "elapsed_s": round(time.monotonic() - started_at, 3),
                }
            if steps >= self._max_steps:
                raise StateMachineError(
                    f"max_steps {self._max_steps} exhausted at state "
                    f"{current!r}",
                )
            current = self._pick_transition(state, current, started_at)
            steps += 1

    def _check_timeout(self, started_at: float, current: str) -> None:
        if time.monotonic() - started_at > self._global_timeout_s:
            raise StateMachineError(
                f"global_timeout_s {self._global_timeout_s} exceeded "
                f"at state {current!r}",
            )

    def _run_on_enter(self, state: Mapping[str, Any]) -> None:
        for action in state.get("on_enter") or []:
            self._execute(action)

    def _pick_transition(self, state: Mapping[str, Any], state_name: str,
                         started_at: float) -> str:
        transitions = state.get("transitions") or []
        entered_at = time.monotonic()
        while True:
            for trans in transitions:
                if self._guard_eval(trans, self._context, entered_at):
                    return self._target(trans, state_name)
            # An ``after`` guard was evaluated once, against the run's start,
            # so a state whose only exit was a timer failed at once. Wait
            # for the earliest pending timer, within the global timeout.
            wait_s = _next_timer_s(transitions, entered_at)
            remaining_s = self._global_timeout_s - (time.monotonic() - started_at)
            if wait_s is None or wait_s > remaining_s:
                # Nothing left that can fire before the global timeout.
                raise StateMachineError(
                    f"no transition fired in state {state_name!r}",
                )
            time.sleep(min(wait_s, _TIMER_POLL_S))
            self._check_timeout(started_at, state_name)

    def _target(self, trans: Mapping[str, Any], state_name: str) -> str:
        target = trans.get("go_to")
        if target not in self._states:
            raise StateMachineError(
                f"transition from {state_name!r} targets undefined "
                f"state {target!r}",
            )
        return target


_TIMER_POLL_S = 0.05


def _next_timer_s(transitions: Any, entered_at: float) -> Optional[float]:
    """Seconds until the earliest ``after`` guard that has not elapsed."""
    elapsed = time.monotonic() - entered_at
    waits = [float(trans["after"]) - elapsed for trans in transitions
             if isinstance(trans, Mapping) and "after" in trans
             and float(trans["after"]) > elapsed]
    return min(waits) if waits else None


def _validate_spec(spec: Mapping[str, Any]) -> None:
    if not isinstance(spec, Mapping):
        raise StateMachineError("spec must be a mapping")
    if "initial" not in spec:
        raise StateMachineError("spec missing 'initial' key")
    if "states" not in spec or not isinstance(spec["states"], Mapping):
        raise StateMachineError("spec missing 'states' mapping")


def _default_execute_action(action: Any) -> Any:
    """Lazy bridge to the main executor; isolates test imports."""
    from je_auto_control.utils.executor.action_executor import execute_action
    return execute_action([action] if not isinstance(action, list) else action)


def _after_ok(transition: Mapping[str, Any], _context: Mapping[str, Any],
              entered_at: float) -> bool:
    return time.monotonic() - entered_at >= float(transition["after"])


def _var_eq_ok(transition: Mapping[str, Any], context: Mapping[str, Any],
               _entered_at: float) -> bool:
    spec = transition["if_var_eq"]
    return context.get(spec.get("name")) == spec.get("value")


def _predicate_ok(transition: Mapping[str, Any], context: Mapping[str, Any],
                  _entered_at: float) -> bool:
    # Caller-supplied callable; the Python route to any custom check.
    pred = transition["predicate"]
    if not callable(pred):
        # A string from JSON ("ctx.ok == True") made the transition always
        # fire; like an unknown if_* guard, it is a spec error.
        raise StateMachineError(f"predicate must be callable, got {pred!r}")
    return bool(pred(context))


def _image_found_ok(transition: Mapping[str, Any], _context: Mapping[str, Any],
                    _entered_at: float) -> bool:
    """``if_image_found``: a template path, or ``{"image", "detect_threshold"}``."""
    spec = transition["if_image_found"]
    image = spec.get("image") if isinstance(spec, Mapping) else spec
    # 1.0 is locate_image_center's own default (an exact match).
    threshold = float(spec.get("detect_threshold", 1.0)) if isinstance(spec, Mapping) else 1.0
    from je_auto_control.utils.exception.exceptions import AutoControlException
    from je_auto_control.wrapper.auto_control_image import locate_image_center
    try:
        locate_image_center(image, detect_threshold=threshold)
    except (AutoControlException, OSError, ValueError):
        return False  # not on screen (or unreadable): the guard does not fire
    return True


_GUARD_CHECKS = (
    ("after", _after_ok),
    ("if_var_eq", _var_eq_ok),
    ("if_image_found", _image_found_ok),
    ("predicate", _predicate_ok),
)
_KNOWN_GUARDS = frozenset(key for key, _check in _GUARD_CHECKS if key.startswith("if_"))


def _default_guard_eval(transition: Mapping[str, Any],
                        context: Mapping[str, Any],
                        entered_at: float) -> bool:
    """Fire when every guard the transition names holds (no guard: always)."""
    _reject_unknown_guards(transition)
    return all(check(transition, context, entered_at)
               for key, check in _GUARD_CHECKS if key in transition)


def _reject_unknown_guards(transition: Mapping[str, Any]) -> None:
    """The docstring once listed if_var / if_image_found / if_pixel, none of
    them implemented: such a transition fired unconditionally."""
    unknown = [key for key in transition
               if key.startswith("if_") and key not in _KNOWN_GUARDS]
    if unknown:
        raise StateMachineError(
            f"unknown guard {unknown[0]!r}; use 'predicate' for other checks")


def run_state_machine(spec: Mapping[str, Any], **kwargs) -> Dict[str, Any]:
    """Convenience wrapper: build a :class:`StateMachine` and run it."""
    return StateMachine(spec, **kwargs).run()


__all__ = ["StateMachine", "StateMachineError", "run_state_machine"]
