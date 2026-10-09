"""Step data model and (de)serialisation between the tree view and AC JSON.

Also what the builder may show of a run: :func:`displayable_record` masks
every secret-named field of every command's result, and
:class:`OneTimeCollector` gathers what it masked while the run reports each
result, for the builder's one-time reveal. Neither writes anything anywhere;
both are free of Qt.
"""
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.executor.action_redaction import (
    FieldPath, MaskedField, masked_fields, record_command, redact_result,
)
from je_auto_control.utils.executor.result_hook import StepPath
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
#: The most one-time values kept for one run; a loop issuing more keeps the first ones.
MAX_ONE_TIME_VALUES = 200


def displayable_record(record: Any) -> Any:
    """A copy of an execution record that is safe to print in the builder.

    Every command's result keeps its shape with every secret-named field
    masked, at any depth, by the rule the executor's result log uses
    (:func:`~je_auto_control.utils.executor.action_redaction.redact_result`);
    the identifiers that rule lists (an approval request's id) stay readable.
    A failure is a string (the error's ``repr``) and is shown as it is. The
    result of a command marked ``sensitive_result`` that has no fields to mask
    by name is hidden whole. The record itself is not changed.
    """
    if not isinstance(record, dict):
        return redact_result(None, record, show_identifiers=True)
    return {key: _shown_result(record_command(key), value) for key, value in record.items()}


def _shown_result(command: Optional[str], value: Any) -> Any:
    if _hidden_whole(command, value):
        return HIDDEN_RESULT
    return redact_result(command, value, show_identifiers=True)


def _hidden_whole(command: Optional[str], value: Any) -> bool:
    """Whether ``value`` is a marked command's result with no named fields (a string is a failure)."""
    spec = COMMAND_SPECS.get(command or "")
    return (spec is not None and spec.sensitive_result
            and value is not None and not isinstance(value, (dict, str)))


@dataclass(frozen=True)
class OneTimeValue:
    """One secret a run produced, with what identifies the step that produced it.

    ``path`` is where the step ran (one
    :class:`~je_auto_control.utils.executor.result_hook.StepPosition` per
    enclosing action list, outermost first), ``subject`` what the command
    acted on (the user id, the secret's name) and ``name`` the result field
    that held the value. ``value`` is left out of the text form, so formatting
    or logging the object never prints it.
    """
    path: StepPath
    command: str
    subject: str
    name: str
    value: str = field(repr=False)

    @property
    def step(self) -> int:
        """The 1-based position of the top-level step the value came from."""
        return self.path[0].position if self.path else 0


class OneTimeCollector:
    """Gathers the secrets of one run as the executor reports each command's result.

    :meth:`note` is the run's result hook
    (``execute_action(actions, result_callback=collector.note)``), so a
    command in the body of a block is seen as well as a top-level one. What
    it keeps of a result is exactly what :func:`displayable_record` masks in
    it. At most ``limit`` values are kept -- the first ones; :meth:`take`
    says whether any were left out. Nothing is stored outside this object.
    """

    def __init__(self, limit: int = MAX_ONE_TIME_VALUES) -> None:
        #: The most values kept for the run.
        self.limit = limit
        self._values: List[OneTimeValue] = []
        self._truncated = False
        self._lock = threading.Lock()

    def note(self, command: str, arguments: Any, result: Any, path: StepPath) -> None:
        """Keep the secrets of ``result``, what ``command`` at ``path`` returned."""
        if _hidden_whole(command, result):
            fields = [MaskedField((), result)]
        else:
            fields = masked_fields(command, result, show_identifiers=True)
        if not fields:
            return
        with self._lock:
            # A block that returns its body's record repeats what the body's steps reported.
            reported = {value.value for value in self._values
                        if len(value.path) > len(path) and value.path[:len(path)] == path}
            for found in fields:
                text = _as_text(found.value)
                if text not in reported:
                    self._keep(OneTimeValue(path, command, _subject(result, arguments, found.path),
                                            _field_name(found.path), text))

    def _keep(self, value: OneTimeValue) -> None:
        if len(self._values) < self.limit:
            self._values.append(value)
        else:
            self._truncated = True

    def take(self) -> Tuple[List[OneTimeValue], bool]:
        """The values kept, in run order, and whether the limit left some out; then forget them."""
        with self._lock:
            values, self._values = self._values, []
            truncated, self._truncated = self._truncated, False
        return values, truncated


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)


def _field_name(path: FieldPath) -> str:
    """``leases[0].token`` for ``("leases", 0, "token")``; a record key is named by its command."""
    name = ""
    for part in path:
        if isinstance(part, int):
            name += f"[{part}]"
        else:
            name += ("." if name else "") + (record_command(part) or str(part))
    return name


_SUBJECT_KEYS = ("user_id", "name")


def _subject(result: Any, arguments: Any, path: FieldPath) -> str:
    """Whom or what a value is for: named beside it in the result, else in the arguments."""
    holder = result
    for part in path[:-1]:
        holder = holder[part]
    for source in (holder, arguments):
        for key in _SUBJECT_KEYS if isinstance(source, dict) else ():
            if isinstance(source.get(key), (str, int)) and source[key] != "":
                return str(source[key])
    return ""


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
