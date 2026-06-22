"""Run a multi-step flow with compensating rollback (the saga pattern).

Some automations span several irreversible-looking steps (create record, send
email, move file). If a later step fails, the already-completed steps should be
*undone* — but the executor's ``AC_try`` only does try/catch/finally for one
block; nothing tracks "what to undo" across N completed steps. A ``Saga`` records
a compensating action per step and, on any failure, runs the compensations for
the completed steps in **LIFO** order.

Forward actions and compensations are plain callables (or, via :func:`run_saga`,
JSON action lists), so the orchestration is fully unit-testable without any real
side effects. Compensation is best-effort: a failing compensation is logged and
the rollback continues. Imports no ``PySide6``.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple


@dataclass
class SagaResult:
    """Outcome of running a saga."""

    ok: bool
    completed: List[str] = field(default_factory=list)
    compensated: List[str] = field(default_factory=list)
    failed_step: Optional[str] = None
    error: str = ""


class Saga:
    """A sequence of steps, each with an optional compensating action."""

    def __init__(self) -> None:
        self._steps: List[Tuple[str, Callable[[], Any],
                                Optional[Callable[[], Any]]]] = []

    def step(self, name: str, action: Callable[[], Any],
             compensation: Optional[Callable[[], Any]] = None) -> "Saga":
        """Append a step; returns self for chaining."""
        self._steps.append((name, action, compensation))
        return self

    def _compensate(self, upto: int, result: SagaResult) -> None:
        for name, _action, compensation in reversed(self._steps[:upto]):
            if compensation is None:
                continue
            try:
                compensation()
            except Exception as error:  # best-effort: log, keep rolling back
                from je_auto_control.utils.logging.logging_instance import (
                    autocontrol_logger)
                autocontrol_logger.warning(
                    "saga compensation for %r failed: %r", name, error)
            result.compensated.append(name)

    def run(self) -> SagaResult:
        """Run steps forward; on failure compensate completed steps LIFO."""
        result = SagaResult(ok=True)
        for index, (name, action, _compensation) in enumerate(self._steps):
            try:
                action()
            except Exception as error:  # noqa: BLE001  # saga catches any step failure
                result.ok = False
                result.failed_step = name
                result.error = str(error)
                self._compensate(index, result)
                return result
            result.completed.append(name)
        return result


def run_saga(steps: Any) -> SagaResult:
    """Run a saga from a JSON-style spec of action lists.

    ``steps`` is a sequence of ``{"name", "action": [...], "compensation":
    [...]}`` mappings; each ``action`` / ``compensation`` is an AutoControl
    action list run through the executor.
    """
    from je_auto_control.utils.executor.action_executor import execute_action

    def _runner(action_list: Any) -> Callable[[], Any]:
        return lambda: execute_action(action_list)

    saga = Saga()
    for spec in steps:
        comp = spec.get("compensation")
        saga.step(str(spec.get("name", "")), _runner(spec.get("action", [])),
                  _runner(comp) if comp else None)
    return saga.run()
