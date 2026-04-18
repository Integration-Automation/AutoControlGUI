"""Step data model and (de)serialisation between the tree view and AC JSON."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS


@dataclass
class Step:
    """A single node in the script tree.

    ``bodies`` maps body key (``body``, ``then``, ``else``) to child steps,
    mirroring the flow-control structure in the executor.
    """
    command: str
    params: Dict[str, Any] = field(default_factory=dict)
    bodies: Dict[str, List["Step"]] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Human-readable label derived from the command and key params."""
        spec = COMMAND_SPECS.get(self.command)
        base = spec.label if spec else self.command
        detail = _summarise_params(self.params)
        return f"{base}  {detail}" if detail else base


def step_to_action(step: Step) -> list:
    """Convert a Step to the executor's action list entry."""
    params: Dict[str, Any] = dict(step.params)
    for body_key, children in step.bodies.items():
        params[body_key] = [step_to_action(child) for child in children]
    if not params:
        return [step.command]
    return [step.command, params]


def action_to_step(action: list) -> Step:
    """Convert a single action entry back to a Step."""
    if not action or not isinstance(action[0], str):
        raise ValueError(f"Invalid action: {action!r}")
    command = action[0]
    raw_params: Mapping[str, Any] = action[1] if len(action) > 1 and isinstance(action[1], dict) else {}
    spec = COMMAND_SPECS.get(command)
    body_keys: Tuple[str, ...] = spec.body_keys if spec else ()

    params: Dict[str, Any] = {}
    bodies: Dict[str, List[Step]] = {}
    for key, value in raw_params.items():
        if key in body_keys and isinstance(value, list):
            bodies[key] = [action_to_step(child) for child in value]
        else:
            params[key] = value
    return Step(command=command, params=params, bodies=bodies)


def actions_to_steps(actions: list) -> List[Step]:
    """Convert a flat action list to a list of Steps."""
    return [action_to_step(entry) for entry in actions]


def steps_to_actions(steps: List[Step]) -> list:
    """Convert a list of Steps back to an AC action list."""
    return [step_to_action(step) for step in steps]


def _summarise_params(params: Mapping[str, Any]) -> str:
    """Produce a compact one-line summary of param values."""
    if not params:
        return ""
    parts = []
    for key, value in list(params.items())[:3]:
        text = str(value)
        if len(text) > 24:
            text = text[:21] + "..."
        parts.append(f"{key}={text}")
    return ", ".join(parts)
