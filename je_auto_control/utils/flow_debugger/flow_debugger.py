"""Step-through debugger and tracer for action lists.

Run an action list one command at a time with breakpoints, single-step,
and live variable inspection — the missing developer affordance for
authoring flows. Stepping reuses one :class:`Executor` instance so script
variables (``${name}`` interpolation, ``AC_set_var`` …) persist across
steps exactly as they would in a normal run.

:func:`trace_actions` is the stateless one-shot form: run a list (or
``dry_run`` to only plan it) and get a per-step trace of command and
result — wired into the executor / MCP / Script Builder.

Pure standard library; imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional


def _new_executor() -> Any:
    """Return a fresh, isolated executor instance."""
    from je_auto_control.utils.executor.action_executor import Executor
    return Executor()


def _command_of(action: Any) -> Optional[str]:
    if isinstance(action, (list, tuple)) and action:
        return action[0] if isinstance(action[0], str) else None
    return None


class FlowDebugger:
    """Step through an action list with breakpoints and variable inspection."""

    def __init__(self, actions: List[Any], *,
                 breakpoints: Optional[List[int]] = None,
                 executor: Any = None) -> None:
        self._actions = list(actions)
        self._breakpoints = {int(b) for b in (breakpoints or ())}
        self._executor = executor
        self._index = 0
        self._record: Dict[str, Any] = {}

    def _exec(self) -> Any:
        if self._executor is None:
            self._executor = _new_executor()
        return self._executor

    @property
    def index(self) -> int:
        """Index of the next action to run."""
        return self._index

    @property
    def finished(self) -> bool:
        """True once every action has run."""
        return self._index >= len(self._actions)

    @property
    def record(self) -> Dict[str, Any]:
        """A copy of the accumulated execution record."""
        return dict(self._record)

    def variables(self) -> Dict[str, Any]:
        """Snapshot of the live script variables."""
        if self._executor is None:
            return {}
        return self._executor.variables.as_dict()

    def peek(self) -> Optional[Any]:
        """Return the next action without running it (or ``None``)."""
        return None if self.finished else self._actions[self._index]

    def set_breakpoint(self, index: int) -> None:
        """Pause before the action at ``index``."""
        self._breakpoints.add(int(index))

    def clear_breakpoint(self, index: int) -> None:
        """Remove a breakpoint if present."""
        self._breakpoints.discard(int(index))

    def step(self) -> Optional[Dict[str, Any]]:
        """Run exactly one action; return ``{index, command, result}``."""
        if self.finished:
            return None
        current = self._index
        action = self._actions[current]
        result = self._exec().execute_action([action])
        self._record.update(result)
        self._index += 1
        return {"index": current, "command": _command_of(action),
                "result": next(iter(result.values()), None)}

    def continue_(self, max_steps: int = 100000) -> List[Dict[str, Any]]:
        """Run until the next breakpoint or the end."""
        executed: List[Dict[str, Any]] = []
        while not self.finished and len(executed) < max_steps:
            if self._index in self._breakpoints and executed:
                break
            executed.append(self.step())
        return executed

    def run_to_end(self) -> List[Dict[str, Any]]:
        """Run every remaining action, ignoring breakpoints."""
        executed: List[Dict[str, Any]] = []
        while not self.finished:
            executed.append(self.step())
        return executed

    def reset(self) -> None:
        """Rewind to the start and clear record and variables."""
        self._index = 0
        self._record = {}
        if self._executor is not None:
            self._executor.variables.clear()


def trace_actions(actions: List[Any], *, dry_run: bool = False,
                  executor: Any = None) -> List[Dict[str, Any]]:
    """Run ``actions`` and return a per-step trace.

    Each entry is ``{index, command, result}``. With ``dry_run`` the
    actions are planned but not executed.
    """
    runner = executor or _new_executor()
    record = runner.execute_action(list(actions), dry_run=dry_run)
    values = list(record.values())
    trace: List[Dict[str, Any]] = []
    for i, action in enumerate(actions):
        trace.append({"index": i, "command": _command_of(action),
                      "result": values[i] if i < len(values) else None})
    return trace
