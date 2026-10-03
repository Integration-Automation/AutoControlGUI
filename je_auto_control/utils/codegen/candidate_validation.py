"""Validate generated inputs against the installed registry without dispatching."""
from __future__ import annotations

import inspect
from typing import Callable, Dict, List, Optional

from je_auto_control.utils.action_journal.events import JSONValue
from je_auto_control.utils.codegen.candidate_models import CandidateError
from je_auto_control.utils.executor.action_schema import BLOCK_REQUIRED_KEYS, validate_actions
from je_auto_control.utils.exception.exceptions import AutoControlException


def validate_candidate_actions(actions: List[List[JSONValue]]) -> Dict[str, JSONValue]:
    """Check shapes, names, Python argument binding and the pure executor dry-run."""
    # pylint: disable-next=import-outside-toplevel  # reason: registry is inspected after facade registration
    from je_auto_control.utils.executor.action_executor import Executor, executor
    probe = Executor()
    probe.event_dict.update(executor.event_dict)
    try:
        validate_actions(actions, probe.known_commands())
        for action in actions:
            command = action[0]
            handler = probe.event_dict.get(command) if isinstance(command, str) else None
            block = command in probe._block_commands  # pylint: disable=protected-access  # reason: match the executor's block-before-event dispatch priority
            _check_arguments(str(command), action[1] if len(action) > 1 else None, handler, block)
        # The existing pure dry-run boundary avoids automatic journal environment
        # setup, secret resolution, callback hooks and device handlers.
        probe._execute_list(actions, True, True, True, None)  # pylint: disable=protected-access  # reason: validated pure dry-run excludes runtime setup
    except (AutoControlException, TypeError, ValueError) as error:
        raise CandidateError('candidate command or argument validation failed') from error
    return {'commands': True, 'arguments': True, 'dry_run': True}


def _check_arguments(command: str, arguments: JSONValue,
                     handler: Optional[Callable[..., object]], block: bool) -> None:
    if block:
        arguments = {} if arguments is None else arguments
        if not isinstance(arguments, dict):
            raise CandidateError('candidate block arguments require an object')
        if any(key not in arguments for key in BLOCK_REQUIRED_KEYS.get(command, ())):
            raise CandidateError('candidate block arguments are missing required fields')
    elif handler is not None:
        _bind(inspect.signature(handler), arguments)


def _bind(signature: inspect.Signature, arguments: JSONValue) -> None:
    if arguments is None:
        signature.bind()
    elif isinstance(arguments, dict):
        signature.bind(**arguments)
    elif isinstance(arguments, list):
        signature.bind(*arguments)
    else:
        raise CandidateError('candidate arguments require an object or positional array')
