"""Step data model and (de)serialisation between the tree view and AC JSON."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS


@dataclass(eq=False)
class Step:
    """A single node in the script tree.

    ``bodies`` maps body key (``body``, ``then``, ``else``) to child steps,
    mirroring the flow-control structure in the executor.

    Equality is identity-based (``eq=False``): the tree keeps its Steps in
    plain lists and locates the *selected* one with ``list.remove``/``index``/
    ``in``. Value equality would match the first structurally-equal Step, so
    deleting or moving one of several duplicate steps corrupted the model.
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
    """Convert a single action entry back to a Step.

    Raises ``ValueError`` for anything that is not a ``[command, params?]``
    list. Without the ``isinstance(action, list)`` guard a string entry was
    silently mis-parsed (``"auto_control"`` became command ``"a"``) and a dict
    entry raised a bare ``KeyError`` instead of a clear message.
    """
    if not isinstance(action, list) or not action or not isinstance(action[0], str):
        raise ValueError(f"Invalid action: {action!r}")
    command = action[0]
    raw_params: Mapping[str, Any] = action[1] if len(action) > 1 and isinstance(action[1], dict) else {}
    spec = COMMAND_SPECS.get(command)
    body_keys: Tuple[str, ...] = spec.body_keys if spec else ()
    params, bodies = _split_params(raw_params, body_keys)
    return Step(command=command, params=params, bodies=bodies)


def _split_params(raw_params: Mapping[str, Any], body_keys: Tuple[str, ...]
                  ) -> Tuple[Dict[str, Any], Dict[str, List[Step]]]:
    """Partition raw params into scalar params and nested body step-lists."""
    params: Dict[str, Any] = {}
    bodies: Dict[str, List[Step]] = {}
    for key, value in raw_params.items():
        if key in body_keys and isinstance(value, list):
            bodies[key] = [action_to_step(child) for child in value]
        else:
            params[key] = value
    return params, bodies


def actions_to_steps(actions: Any) -> List[Step]:
    """Convert an action list (or ``{"auto_control": [...]}`` wrapper) to Steps.

    Mirrors what the executor accepts. Any other shape raises ``ValueError``
    rather than fabricating placeholder Steps that a later Save would write
    back over the user's file.
    """
    return [action_to_step(entry) for entry in _unwrap_action_list(actions)]


def _unwrap_action_list(actions: Any) -> list:
    """Return the bare action list, unwrapping the ``auto_control`` mapping."""
    if isinstance(actions, dict):
        wrapped = actions.get("auto_control")
        if wrapped is None:
            raise ValueError("Action mapping has no 'auto_control' key")
        actions = wrapped
    if not isinstance(actions, list):
        raise ValueError(
            f"Expected an action list, got {type(actions).__name__}"
        )
    return actions


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
