"""High-level helper around Anthropic's Computer-Use agent loop.

Wraps :class:`ComputerUseAgentBackend` + :class:`AgentLoop` so callers
only need to provide a natural-language ``goal`` — display dimensions,
budgets, screenshot capture, and tool dispatch all have sensible
defaults. Same headless API powers the executor command, MCP tool and
GUI panel.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from je_auto_control.utils.agent.agent_loop import (
    AgentBudget, AgentLoop, AgentResult, AgentStep,
)
from je_auto_control.utils.agent.backends import (
    AgentBackendError, ComputerUseAgentBackend,
)


_DEFAULT_MAX_STEPS = 25
_DEFAULT_WALL_SECONDS = 300.0
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_MODEL = "claude-opus-4-7"


def _resolve_display() -> tuple[int, int]:
    """Read the primary monitor's pixel size for the computer-use schema."""
    try:
        from je_auto_control.wrapper.auto_control_screen import screen_size
        width, height = screen_size()
        return int(width), int(height)
    except (ImportError, OSError, RuntimeError) as exc:
        raise AgentBackendError(
            "could not auto-detect display size; pass display_width_px / "
            "display_height_px explicitly",
        ) from exc


def run_computer_use(goal: str,
                     *,
                     display_width_px: Optional[int] = None,
                     display_height_px: Optional[int] = None,
                     display_number: Optional[int] = None,
                     max_steps: int = _DEFAULT_MAX_STEPS,
                     wall_seconds: float = _DEFAULT_WALL_SECONDS,
                     model: str = _DEFAULT_MODEL,
                     max_tokens: int = _DEFAULT_MAX_TOKENS,
                     api_key: Optional[str] = None,
                     client: Optional[Any] = None,
                     backend: Optional[ComputerUseAgentBackend] = None,
                     ) -> AgentResult:
    """Drive Anthropic Computer-Use until ``goal`` is met or the budget hits.

    Auto-detects display dimensions when not passed. ``backend`` lets
    tests inject a fake without bringing in the SDK.
    """
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("run_computer_use requires a non-empty goal string")
    if backend is None:
        width = display_width_px or _resolve_display()[0]
        height = display_height_px or _resolve_display()[1]
        backend = ComputerUseAgentBackend(
            display_width_px=int(width),
            display_height_px=int(height),
            display_number=display_number,
            client=client, api_key=api_key,
            model=model, max_tokens=int(max_tokens),
        )
    budget = AgentBudget(
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
    )
    return AgentLoop(backend, budget=budget).run(goal)


def result_to_dict(result: AgentResult) -> Dict[str, Any]:
    """Render an :class:`AgentResult` as JSON-friendly nested dicts."""
    return {
        "succeeded": bool(result.succeeded),
        "final_message": result.final_message,
        "elapsed_s": float(result.elapsed_s),
        "steps": [_step_to_dict(step) for step in result.steps],
    }


def _step_to_dict(step: AgentStep) -> Dict[str, Any]:
    data = asdict(step)
    result = data.get("result")
    if not isinstance(result, (str, int, float, bool, list, dict, type(None))):
        data["result"] = repr(result)
    return data


def steps_to_dicts(steps: List[AgentStep]) -> List[Dict[str, Any]]:
    """Convenience for the MCP / executor adapters."""
    return [_step_to_dict(step) for step in steps]


__all__ = [
    "result_to_dict", "run_computer_use", "steps_to_dicts",
]
