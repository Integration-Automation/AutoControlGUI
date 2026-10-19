"""Normalize recorded action shapes and validate source without resolving or dispatching inputs."""
import ast
import inspect
import json
from typing import Callable, cast

from je_auto_control.utils.action_journal.capture import bound_journal
from je_auto_control.utils.action_journal.redaction import sanitize_event
from je_auto_control.utils.action_lint.linter import ActionLinter
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError
from je_auto_control.utils.codegen.journal_source import unique_object
from je_auto_control.utils.codegen.journal_steps import JournalStep
from je_auto_control.utils.executor.action_schema import FLOW_BODY_KEYS, FLOW_BRANCH_LIST_KEYS, validate_actions
from je_auto_control.utils.logging.secret_scope import scrub_secret_data

Action = list[object]
_OUTCOME_REASONS = {"redacted_outcome", "redacted_error"}


def prepare_action(step: JournalStep) -> tuple[Action, tuple[str, ...]]:
    """Preserve unresolved references, refuse masked inputs and normalize legacy positional snapshots."""
    event = step.event
    wire = sanitize_event(event)
    params = cast(dict[str, object], wire["parameters"])
    reasons = set(cast(list[str], wire["non_replayable"])) - _OUTCOME_REASONS
    safe = scrub_secret_data(params)
    if safe != params:
        reasons.add("resolved_secret_redacted")
    if _masked(params):
        reasons.add("masked_or_unsupported_input")
    action: Action = [event.command, params]
    if set(params) == {"args"} and not _mapping_binds(event.command, params):
        args = params["args"]
        if args == []:
            action = [event.command]
        elif isinstance(args, list) and len(args) == 1 and isinstance(args[0], list):
            action = [event.command, args[0]]
    return action, tuple(sorted(reasons))


def _body_parameters(command: str, params: dict[str, object], depth: int) -> dict[str, object]:
    if depth > 32:
        raise CandidateGenerationError("recorded action hierarchy exceeds 32 levels")
    result = dict(params)
    for key in FLOW_BODY_KEYS.get(command, ()):
        if key in result:
            if isinstance(result[key], str):
                raise CandidateGenerationError("recorded control body must be a structured action list")
            result[key] = _body(result[key], depth)
    for key in FLOW_BRANCH_LIST_KEYS.get(command, ()):
        if key in result:
            result[key] = _branch_bodies(result[key], depth)
    return result


def _decoded(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return []
    return json.loads(value, object_pairs_hook=unique_object) if isinstance(value, str) else value


def _body(value: object, depth: int) -> object:
    decoded = value
    if not isinstance(decoded, list):
        return decoded
    result = []
    for action in decoded:
        if (isinstance(action, list) and len(action) == 2
                and isinstance(action[0], str) and isinstance(action[1], dict)):
            result.append([action[0], _body_parameters(action[0], action[1], depth + 1)])
        else:
            result.append(action)
    return result


def _branch_bodies(value: object, depth: int) -> list[object]:
    branches = _decoded(value)
    if branches is None:
        return []
    if not isinstance(branches, list) or any(not isinstance(branch, list) for branch in branches):
        raise CandidateGenerationError("recorded parallel branches must be action lists")
    return [_body(branch, depth) for branch in branches]


def _masked(value: object) -> bool:
    if isinstance(value, str):
        return "***" in value
    if isinstance(value, dict):
        return "unsupported" in value or any(_masked(item) for item in value.values())
    if isinstance(value, list):
        return any(_masked(item) for item in value)
    return False


def _mapping_binds(command: str, params: dict[str, object]) -> bool:
    # pylint: disable-next=import-outside-toplevel  # reason: codegen is imported by the executor facade
    from je_auto_control.utils.executor.action_executor import executor
    function = executor.event_dict.get(command)
    if function is None:
        return False
    try:
        inspect.signature(function).bind(**params)
    except (TypeError, ValueError):
        return False
    return True


def validate_candidate_actions(actions: list[Action]) -> None:
    """Check command names, nested schemas and actual call signatures; never resolve variables."""
    # pylint: disable-next=import-outside-toplevel  # reason: avoid initialization-time executor cycles
    from je_auto_control.utils.executor.action_executor import executor
    normalized = [_normalized_action(action) for action in actions]
    validate_actions(normalized, executor.known_commands())
    if ActionLinter().lint_actions(normalized):
        raise CandidateGenerationError("recorded actions fail command schema validation")
    pending = list(normalized)
    count = 0
    while pending:
        action = pending.pop()
        count += 1
        if count > 10000:
            raise CandidateGenerationError("candidate exceeds 10000 action nodes")
        name = cast(str, action[0])
        params = action[1] if len(action) == 2 else {}
        if name in executor.event_dict:
            _bind(executor.event_dict[name], params)
        if isinstance(params, dict):
            pending.extend(cast(list[Action], _children(name, params)))


def _bind(function: Callable[..., object], params: object) -> None:
    try:
        signature = inspect.signature(function)
        if isinstance(params, dict):
            signature.bind(**params)
        elif isinstance(params, list):
            signature.bind(*params)
        else:
            raise CandidateGenerationError("recorded arguments have no supported call shape")
    except (TypeError, ValueError):
        raise CandidateGenerationError("recorded arguments do not match the command signature") from None


def _children(name: str, params: dict[str, object]) -> list[object]:
    result: list[object] = []
    for key in FLOW_BODY_KEYS.get(name, ()):
        body = params.get(key)
        if isinstance(body, list):
            result.extend(body)
    for key in FLOW_BRANCH_LIST_KEYS.get(name, ()):
        branches = params.get(key)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, list):
                    result.extend(branch)
    return result


def source_children(action: Action) -> list[object]:
    """Inspect structured/encoded branch bodies without rewriting the source emitted for replay."""
    name = cast(str, action[0])
    params = action[1] if len(action) == 2 else {}
    return _children(name, _body_parameters(name, params, 0)) if isinstance(params, dict) else []


def _normalized_action(action: Action) -> Action:
    if len(action) == 2 and isinstance(action[0], str) and isinstance(action[1], dict):
        return [action[0], _body_parameters(action[0], action[1], 0)]
    return action


def validate_generated_code(code: str, target: str) -> None:
    """Parse Python artifacts or the trusted Robot renderer's embedded Python expressions."""
    if target != "robot":
        ast.parse(code)
        return
    for line in code.splitlines():
        _, separator, expression = line.partition("    Evaluate    ")
        if separator:
            expression = expression.removesuffix("    base64,json").replace("$actions", "actions")
            ast.parse(expression, mode="eval")


def dry_run_candidate(actions: list[Action]) -> None:
    """Use the real dry-run path with journal capture unbound, never dispatching input or resolving secrets."""
    # pylint: disable-next=import-outside-toplevel  # reason: the executor imports codegen adapters
    from je_auto_control.utils.executor.action_executor import executor
    if actions:
        with bound_journal(None):
            executor.execute_action(actions, dry_run=True, raise_on_error=True)
