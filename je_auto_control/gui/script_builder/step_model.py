"""Step data model and (de)serialisation between the tree view and AC JSON.

Also what the builder may show of a run: :func:`displayable_record` masks the
results of commands whose schema entry is marked ``sensitive_result``, and
:func:`one_time_values` lists what it masked, for the builder's one-time
reveal. Neither writes anything anywhere; both are free of Qt.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.executor.action_redaction import SENSITIVE_ARGUMENT_NAMES
from je_auto_control.utils.json.json_file import read_action_json, write_action_json


@dataclass(eq=False)
class Step:
    """A single node in the script tree.

    ``bodies`` maps body key (``body``, ``then``, ``else``) to child steps,
    mirroring the flow-control structure in the executor.

    Equality is identity-based (``eq=False``): the tree keeps its Steps in
    plain lists and locates the *selected* one with ``list.remove``/``index``/
    ``in``. Value equality would match the first structurally-equal Step, so
    deleting or moving one of several duplicate steps corrupted the model.

    ``args`` holds positional arguments (``[command, [arg, ...]]``, which the
    executor accepts). The form does not edit them; they are kept verbatim.
    """
    command: str
    params: Dict[str, Any] = field(default_factory=dict)
    bodies: Dict[str, List["Step"]] = field(default_factory=dict)
    args: Optional[List[Any]] = None

    @property
    def label(self) -> str:
        """Human-readable label derived from the command and key params."""
        spec = COMMAND_SPECS.get(self.command)
        base = spec.label if spec else self.command
        detail = _summarise_params(self.params) if self.args is None else _summarise_args(self.args)
        return f"{base}  {detail}" if detail else base


#: Shown in place of a marked command's result that is not a mapping.
HIDDEN_RESULT = "(hidden: this command's result carries a secret)"
_MASK = "***"
# A record key is "execute: " + str(action); the command is its first element.
_RECORD_COMMAND = re.compile(r"^execute: \['(AC_\w+)'")


def displayable_record(record: Any) -> Any:
    """A copy of an execution record that is safe to print in the builder.

    The result of a command marked ``sensitive_result`` -- at the top level or
    inside a block's nested record -- keeps its shape with every secret-named
    field masked, so the row still says which user it was. A failure is a
    string (the error's ``repr``) and is shown as it is. The record itself is
    not changed.
    """
    if isinstance(record, list):
        return [displayable_record(item) for item in record]
    if not isinstance(record, dict):
        return record
    shown: Dict[Any, Any] = {}
    for key, value in record.items():
        if _marked_command(key) is not None:
            shown[key] = _without_secrets(value)
        else:
            shown[key] = displayable_record(value)
    return shown


def _marked_command(key: Any) -> Optional[str]:
    """The command of record key ``key`` when its result is marked sensitive."""
    match = _RECORD_COMMAND.match(key) if isinstance(key, str) else None
    if match is None:
        return None
    spec = COMMAND_SPECS.get(match.group(1))
    return match.group(1) if spec is not None and spec.sensitive_result else None


@dataclass(frozen=True)
class OneTimeValue:
    """One secret a run produced, with what identifies the step that produced it.

    ``step`` is the 1-based position of the top-level step in the run,
    ``subject`` what the command acted on (the user id) and ``name`` the
    result field that held the value. ``value`` is left out of the text form,
    so formatting or logging the object never prints it.
    """
    step: int
    command: str
    subject: str
    name: str
    value: str = field(repr=False)


def one_time_values(record: Any) -> List[OneTimeValue]:
    """Every secret :func:`displayable_record` would mask in ``record``, in run order.

    A command that failed (its result is the error's text) produced none. The
    record is only read.
    """
    found: List[OneTimeValue] = []
    if isinstance(record, dict):
        for position, (key, value) in enumerate(record.items(), start=1):
            _collect_secrets(key, value, position, found)
    return found


def _collect_secrets(key: Any, value: Any, step: int, found: List[OneTimeValue]) -> None:
    command = _marked_command(key)
    if command is not None:
        found.extend(_secrets_of(step, command, value))
        return
    for nested_key, nested in _entries(value):
        _collect_secrets(nested_key, nested, step, found)


def _entries(value: Any) -> Iterator[Tuple[Any, Any]]:
    """The ``(key, item)`` pairs of a container; a list's items have no key."""
    if isinstance(value, dict):
        yield from value.items()
    elif isinstance(value, list):
        for item in value:
            yield None, item


def _secrets_of(step: int, command: str, value: Any) -> List[OneTimeValue]:
    """What a marked command's result holds that the display hides."""
    if value is None or isinstance(value, str):
        return []
    if not isinstance(value, dict):
        text = json.dumps(value, default=str, ensure_ascii=False)
        return [OneTimeValue(step, command, "", "", text)]
    subject = str(value.get("user_id", ""))
    return [OneTimeValue(step, command, subject, str(name), str(item))
            for name, item in value.items()
            if str(name).lower() in SENSITIVE_ARGUMENT_NAMES and item not in (None, "")]


def nested_sensitive_commands(actions: Any) -> List[str]:
    """The marked commands that sit inside a block of ``actions``, sorted.

    A block (``AC_loop``, ``AC_if_*``, ``AC_try``...) records its own summary,
    not the results of the commands in its body, so a secret issued there is in
    no record and cannot be revealed afterwards.
    """
    names: Set[str] = set()
    for action in actions if isinstance(actions, list) else []:
        for argument in action[1:] if isinstance(action, list) else []:
            _nested_marked(argument, names)
    return sorted(names)


def _nested_marked(value: Any, names: Set[str]) -> None:
    if isinstance(value, list) and value and isinstance(value[0], str) and value[0] in COMMAND_SPECS:
        if COMMAND_SPECS[value[0]].sensitive_result:
            names.add(value[0])
        value = value[1:]
    for _key, item in _entries(value):
        _nested_marked(item, names)


def _without_secrets(value: Any) -> Any:
    """``value`` with its secret-named fields masked; hidden whole when it has no fields."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return HIDDEN_RESULT
    return {key: _MASK if str(key).lower() in SENSITIVE_ARGUMENT_NAMES else item
            for key, item in value.items()}


def step_to_action(step: Step) -> list:
    """Convert a Step to the executor's action list entry."""
    if step.args is not None:
        return [step.command, list(step.args)]
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

    Positional arguments (``[command, [arg, ...]]``) become ``Step.args``. They
    used to be dropped, as was anything after the second entry, so Save wrote
    ``[command]`` back over the user's file.
    """
    if (not isinstance(action, list) or not 1 <= len(action) <= 2
            or not isinstance(action[0], str)):
        raise ValueError(f"Invalid action: {action!r}")
    command = action[0]
    if len(action) == 2 and isinstance(action[1], list):
        return Step(command=command, args=list(action[1]))
    if len(action) == 2 and not isinstance(action[1], dict):
        raise ValueError(f"Arguments of {command} must be an object or a list: {action[1]!r}")
    raw_params: Mapping[str, Any] = action[1] if len(action) == 2 else {}
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


def load_action_file(path: str) -> Tuple[List[Step], Optional[Dict[str, Any]]]:
    """Read an action file as Steps, with the other keys of a wrapped file.

    The second value is ``None`` for a bare list, and otherwise everything but
    ``auto_control``, for :func:`save_action_file` to write back. Raises the
    reader's ``AutoControlException`` or ``ValueError`` for a bad file.
    """
    actions = read_action_json(path)
    steps = actions_to_steps(actions)
    if not isinstance(actions, dict):
        return steps, None
    return steps, {key: value for key, value in actions.items() if key != "auto_control"}


def save_action_file(path: str, steps: List[Step], extras: Optional[Dict[str, Any]] = None) -> None:
    """Write ``steps`` to ``path``, wrapped with ``extras`` when a file had them."""
    actions = steps_to_actions(steps)
    write_action_json(path, actions if extras is None else {**extras, "auto_control": actions})


def _summarise_args(args: List[Any]) -> str:
    """One-line summary of positional arguments."""
    text = ", ".join(str(value) for value in args[:3])
    return f"({text[:40]}...)" if len(text) > 40 else f"({text})"


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
