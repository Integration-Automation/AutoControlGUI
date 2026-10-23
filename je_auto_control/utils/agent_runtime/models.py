"""Detached JSON contracts for managed computer tasks and their evidence."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

STATES = frozenset({"queued", "running", "pausing", "paused", "waiting_user", "recovering", "verifying",
                    "cancelling", "succeeded", "failed", "cancelled", "timed_out"})
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "timed_out"})
MODES = frozenset({"external", "ollama", "skill"})


def detached(value: Any) -> Any:
    """Return bounded JSON data, refusing non-finite numbers and arbitrary objects."""
    try:
        encoded = json.dumps(thaw(value), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 1_000_000:
            raise AgentTaskError("task data exceeds one megabyte")
        data = json.loads(encoded)
        pending = [(data, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 32:
                raise AgentTaskError("task data nesting exceeds 32 levels")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        return data
    except (TypeError, ValueError, RecursionError) as error:
        raise AgentTaskError("task data must be finite bounded JSON") from error


def thaw(value: Any) -> Any:
    """Convert immutable contract containers to independent JSON containers."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


def freeze(value: Any) -> Any:
    """Recursively freeze already validated JSON data."""
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def positive(value: Any, name: str, maximum: float) -> None:
    """Require a finite positive numeric budget, excluding boolean values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentTaskError(f"{name} must be numeric")
    if not math.isfinite(value) or not 0 < value <= maximum:
        raise AgentTaskError(f"{name} must be positive and at most {maximum}")


@dataclass(frozen=True)
class AgentTaskBudget:
    """Finite execution limits; a deadline always bounds individual operations."""

    max_steps: int = 25
    wall_seconds: float = 300.0
    retries: int = 2
    action_seconds: float = 30.0
    model_seconds: float = 120.0

    def __post_init__(self) -> None:
        positive(self.max_steps, "max_steps", 100_000)
        positive(self.wall_seconds, "wall_seconds", 86_400)
        positive(self.action_seconds, "action_seconds", 3600)
        positive(self.model_seconds, "model_seconds", 3600)
        if not isinstance(self.max_steps, int) or isinstance(self.retries, bool) or not isinstance(self.retries, int):
            raise AgentTaskError("step and retry budgets must be integers")
        if not 0 <= self.retries <= 10:
            raise AgentTaskError("retries must be between zero and ten")

    def to_dict(self) -> dict[str, Any]:
        """Serialize detached budget values."""
        return {item.name: getattr(self, item.name) for item in fields(self)}


@dataclass(frozen=True)
class AgentTaskSpec:
    """An explicitly authorized goal, target, tool scope and completion criteria."""

    goal: str
    target: str = "local-desktop"
    mode: str = "external"
    allowed_tools: tuple[str, ...] = ()
    success_criteria: tuple[Mapping[str, Any], ...] = ()
    roots: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    inputs: Mapping[str, Any] = field(default_factory=dict)
    actions: tuple[Mapping[str, Any], ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)
    budget: AgentTaskBudget = field(default_factory=AgentTaskBudget)

    def __post_init__(self) -> None:
        self._validate_identity()
        self._freeze_names()
        if not self.allowed_tools or not self.success_criteria:
            raise AgentTaskError("a task requires allowed tools and real completion conditions")
        self._freeze_payload()
        if not isinstance(self.budget, AgentTaskBudget):
            raise AgentTaskError("invalid task budget")

    def _validate_identity(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip() or len(self.goal) > 16_000:
            raise AgentTaskError("a task requires a nonempty bounded goal")
        if not isinstance(self.mode, str) or self.mode not in MODES:
            raise AgentTaskError("unknown task mode")
        if not isinstance(self.target, str) or not self.target:
            raise AgentTaskError("unknown task mode or empty target")

    def _freeze_names(self) -> None:
        for name in ("allowed_tools", "roots", "apps"):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or not all(isinstance(item, str) and item for item in value):
                raise AgentTaskError(f"{name} must be a list of nonempty strings")
            object.__setattr__(self, name, tuple(value))

    def _freeze_payload(self) -> None:
        for name in ("success_criteria", "inputs", "actions", "options"):
            object.__setattr__(self, name, freeze(detached(getattr(self, name))))
        if not isinstance(self.inputs, Mapping) or not isinstance(self.options, Mapping):
            raise AgentTaskError("inputs and options must be objects")
        if not isinstance(self.success_criteria, tuple) or not isinstance(self.actions, tuple):
            raise AgentTaskError("criteria and actions must be arrays")
        if not all(isinstance(item, Mapping) for item in (*self.success_criteria, *self.actions)):
            raise AgentTaskError("criteria and actions must contain objects")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AgentTaskSpec:
        """Validate a JSON specification and detach it from all caller-owned data."""
        if not isinstance(value, Mapping):
            raise AgentTaskError("task specification must be an object")
        data = detached(value)
        try:
            if "budget" in data:
                data["budget"] = AgentTaskBudget(**data["budget"])
            return cls(**data)
        except (TypeError, KeyError) as error:
            raise AgentTaskError("unknown or invalid task specification fields") from error

    def to_dict(self) -> dict[str, Any]:
        """Return independent, JSON-compatible task fields."""
        data = {item.name: thaw(getattr(self, item.name)) for item in fields(self) if item.name != "budget"}
        return {**data, "budget": self.budget.to_dict()}


@dataclass(frozen=True)
class AgentTaskHandle:
    """Stable task identifier returned by submission."""

    task_id: str
    state: str = "queued"


@dataclass(frozen=True)
class AgentObservation:
    """One target observation; indexed elements are valid only within its identifier."""

    observation_id: str
    task_id: str
    captured_at: float
    data: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize observation metadata and detached element data."""
        return {"observation_id": self.observation_id, "task_id": self.task_id,
                "captured_at": self.captured_at, "data": thaw(self.data)}


@dataclass(frozen=True)
class AgentActionRequest:
    """One offered tool call grounded in a particular observation."""

    tool: str
    observation_id: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AgentActionRequest:
        """Reject private, unexpected and non-object action inputs."""
        try:
            request = cls(**detached(value))
        except TypeError as error:
            raise AgentTaskError("invalid action request") from error
        if not isinstance(request.arguments, Mapping):
            raise AgentTaskError("action arguments must be an object")
        if not isinstance(request.tool, str) or not isinstance(request.observation_id, str):
            raise AgentTaskError("action tool and observation_id must be strings")
        return cls(request.tool, request.observation_id, freeze(request.arguments))


@dataclass(frozen=True)
class AgentActionResult:
    """Observed raw action result, with explicit side-effect certainty."""

    action_id: str
    result: Any
    status: str = "confirmed"

    def to_dict(self) -> dict[str, Any]:
        """Return an independent result payload."""
        return {"action_id": self.action_id, "result": thaw(self.result), "status": self.status}


@dataclass(frozen=True)
class AgentTaskResult:
    """Current task state and deterministic completion evidence."""

    task_id: str
    state: str
    goal: str
    reason: str = ""
    steps: int = 0
    verification: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return independent JSON-compatible status and evidence."""
        return {item.name: thaw(getattr(self, item.name)) for item in fields(self)}
