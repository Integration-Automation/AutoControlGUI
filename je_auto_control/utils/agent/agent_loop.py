"""Closed-loop driver: observe → plan → act → verify → loop."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass
class AgentBudget:
    """Per-run safety budgets so a runaway agent can't drain the API."""
    max_steps: int = 25
    wall_seconds: float = 300.0


@dataclass
class AgentStep:
    """One observation / decision / execution triple."""
    index: int
    tool: Optional[str]
    arguments: Optional[Dict[str, Any]]
    result: Any = None
    error: Optional[str] = None
    stop_reason: Optional[str] = None


@dataclass
class AgentResult:
    """Aggregated outcome of an agent run."""
    succeeded: bool
    steps: List[AgentStep] = field(default_factory=list)
    final_message: Optional[str] = None
    elapsed_s: float = 0.0


_STOP = "stop"


class AgentBackend:
    """Pluggable LLM interface — decide_next_action turns observation into a tool call.

    Implementations receive the goal, the latest screenshot bytes, and
    the conversation history. They return ``{"tool": "AC_*", "input":
    {...}}`` to act, or ``{"stop": True, "message": "..."}`` to halt.
    """

    def decide_next_action(self,
                           goal: str,
                           screenshot: Optional[bytes],
                           history: Sequence[AgentStep],
                           ) -> Dict[str, Any]:
        raise NotImplementedError


class FakeAgentBackend(AgentBackend):
    """Test-only backend that replays a fixed script of decisions."""

    def __init__(self, decisions: Sequence[Dict[str, Any]]) -> None:
        self._decisions = list(decisions)
        self._cursor = 0

    def decide_next_action(self, goal, screenshot, history):  # noqa: D401
        if self._cursor >= len(self._decisions):
            return {"stop": True, "message": "fake backend exhausted"}
        decision = self._decisions[self._cursor]
        self._cursor += 1
        return dict(decision)


_DEFAULT_SCREENSHOT_FN: Optional[Callable[[], Optional[bytes]]] = None


def _default_screenshot() -> Optional[bytes]:
    """Pull a PNG of the current screen via the existing helper."""
    try:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        from io import BytesIO
        image = pil_screenshot()
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except (ImportError, OSError, RuntimeError):
        return None


class AgentLoop:
    """The closed-loop driver. Everything injectable for headless tests."""

    def __init__(self,
                 backend: AgentBackend,
                 *, tool_runner: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
                 screenshot_fn: Optional[Callable[[], Optional[bytes]]] = None,
                 budget: Optional[AgentBudget] = None) -> None:
        self._backend = backend
        self._tool_runner = tool_runner or _default_tool_runner
        self._screenshot_fn = screenshot_fn or _default_screenshot
        self._budget = budget or AgentBudget()

    def run(self, goal: str) -> AgentResult:
        started_at = time.monotonic()
        result = AgentResult(succeeded=False)
        metrics = _agent_metrics()
        if metrics:
            metrics["runs"].inc()
        from je_auto_control.utils.observability import default_tracer
        tracer = default_tracer()
        with tracer.start_as_current_span(
                "agent_loop.run", {"goal": goal[:120]},
        ):
            self._run_loop(goal, started_at, result, metrics)
        result.elapsed_s = round(time.monotonic() - started_at, 3)
        if metrics:
            outcome = "succeeded" if result.succeeded else "failed"
            metrics["outcome"].inc(labels={"outcome": outcome})
        return result

    def _run_loop(self, goal: str, started_at: float,
                  result: AgentResult, metrics) -> None:
        for index in range(self._budget.max_steps):
            if time.monotonic() - started_at > self._budget.wall_seconds:
                result.final_message = "wall_seconds budget exhausted"
                return
            if self._take_one_step(goal, index, result, metrics):
                return
        result.final_message = "max_steps budget exhausted"

    def _take_one_step(self, goal: str, index: int,
                       result: AgentResult, metrics) -> bool:
        """Run one observe→decide→act cycle. Returns True when the loop should stop."""
        decision = self._backend.decide_next_action(
            goal, self._screenshot_fn(), result.steps,
        )
        if decision.get("stop"):
            result.succeeded = True
            result.final_message = decision.get("message")
            result.steps.append(AgentStep(
                index=index, tool=None, arguments=None,
                stop_reason=result.final_message,
            ))
            return True
        tool = decision.get("tool")
        if not isinstance(tool, str):
            result.final_message = f"backend returned no tool: {decision!r}"
            return True
        step = self._dispatch_tool(index, tool, decision.get("input") or {})
        result.steps.append(step)
        if metrics:
            outcome = "error" if step.error else "ok"
            metrics["steps"].inc(labels={"tool": tool, "outcome": outcome})
        return False

    def _dispatch_tool(self, index: int, tool: str,
                       args: Dict[str, Any]) -> "AgentStep":
        from je_auto_control.utils.observability import default_tracer
        step = AgentStep(index=index, tool=tool, arguments=dict(args))
        with default_tracer().start_as_current_span(
                "agent_loop.tool_call", {"tool": tool},
        ):
            try:
                step.result = self._tool_runner(tool, args)
            except (ValueError, RuntimeError, OSError) as error:
                step.error = f"{type(error).__name__}: {error}"
        return step


def _default_tool_runner(name: str, args: Dict[str, Any]) -> Any:
    """Default tool dispatch goes through the executor."""
    from je_auto_control.utils.tool_use_schema import run_tool_call
    return run_tool_call(name, args)


_AGENT_METRIC_CACHE: Dict[str, Any] = {}


def _agent_metrics():
    """Lazy-register agent-loop metrics into the default Prometheus registry."""
    if "runs" in _AGENT_METRIC_CACHE:
        return _AGENT_METRIC_CACHE
    try:
        from je_auto_control.utils.observability import (
            Counter, default_registry,
        )
        registry = default_registry()
    except ImportError:
        return None
    _AGENT_METRIC_CACHE["runs"] = registry.register(Counter(
        "autocontrol_agent_runs_total",
        "Number of AgentLoop runs started.",
    ))
    _AGENT_METRIC_CACHE["steps"] = registry.register(Counter(
        "autocontrol_agent_steps_total",
        "Number of AgentLoop steps executed, partitioned by tool + outcome.",
        label_names=("tool", "outcome"),
    ))
    _AGENT_METRIC_CACHE["outcome"] = registry.register(Counter(
        "autocontrol_agent_outcomes_total",
        "Final outcome of each AgentLoop run.",
        label_names=("outcome",),
    ))
    return _AGENT_METRIC_CACHE


def run_agent(goal: str, backend: AgentBackend, **kwargs) -> AgentResult:
    """Convenience wrapper: ``AgentLoop(backend, **kwargs).run(goal)``."""
    return AgentLoop(backend, **kwargs).run(goal)


__all__ = [
    "AgentBackend", "FakeAgentBackend",
    "AgentBudget", "AgentLoop", "AgentResult", "AgentStep",
    "run_agent",
]
