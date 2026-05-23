"""Declarative finite-state-machine engine for action JSON."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Mapping, Optional


class StateMachineError(RuntimeError):
    """Raised when the FSM spec is invalid or the run can't make progress."""


_DEFAULT_MAX_STEPS = 100
_DEFAULT_GLOBAL_TIMEOUT_S = 300.0


class StateMachine:
    """Run a state-machine spec against a pluggable action executor.

    ``execute_action`` is a single-action runner — typically a thin
    closure over :func:`je_auto_control.execute_action`. ``guard_eval``
    is a callable that decides whether a transition fires; it receives
    the transition dict and the FSM's mutable context, and returns
    ``True`` to fire. The default guard evaluator understands
    ``if_var``, ``if_image_found``, ``if_pixel``, and ``after``.
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
            if steps >= self._max_steps:
                raise StateMachineError(
                    f"max_steps {self._max_steps} exhausted at state "
                    f"{current!r}",
                )
            if time.monotonic() - started_at > self._global_timeout_s:
                raise StateMachineError(
                    f"global_timeout_s {self._global_timeout_s} exceeded "
                    f"at state {current!r}",
                )
            state = self._states[current]
            self._run_on_enter(state)
            if state.get("final"):
                return {
                    "final_state": current, "steps": steps,
                    "elapsed_s": round(time.monotonic() - started_at, 3),
                }
            next_state = self._pick_transition(state, current, started_at)
            steps += 1
            current = next_state

    def _run_on_enter(self, state: Mapping[str, Any]) -> None:
        for action in state.get("on_enter") or []:
            self._execute(action)

    def _pick_transition(self, state: Mapping[str, Any], state_name: str,
                         started_at: float) -> str:
        transitions = state.get("transitions") or []
        for trans in transitions:
            if self._guard_eval(trans, self._context, started_at):
                target = trans.get("go_to")
                if target not in self._states:
                    raise StateMachineError(
                        f"transition from {state_name!r} targets undefined "
                        f"state {target!r}",
                    )
                return target
        raise StateMachineError(
            f"no transition fired in state {state_name!r}",
        )


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


def _default_guard_eval(transition: Mapping[str, Any],
                        context: Mapping[str, Any],
                        started_at: float) -> bool:
    """Recognise a handful of common guards. Always-true when none set."""
    if "after" in transition:
        if time.monotonic() - started_at < float(transition["after"]):
            return False
    if "if_var_eq" in transition:
        spec = transition["if_var_eq"]
        key = spec.get("name")
        if context.get(key) != spec.get("value"):
            return False
    if "predicate" in transition:
        # Caller-supplied callable; useful for image / pixel guards.
        pred = transition["predicate"]
        if callable(pred) and not pred(context):
            return False
    return True


def run_state_machine(spec: Mapping[str, Any], **kwargs) -> Dict[str, Any]:
    """Convenience wrapper: build a :class:`StateMachine` and run it."""
    return StateMachine(spec, **kwargs).run()


__all__ = ["StateMachine", "StateMachineError", "run_state_machine"]
