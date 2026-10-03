"""Generate reviewed candidates from validated selected-run journal snapshots."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple

from je_auto_control.utils.action_journal.events import ActionEvent, JSONValue, JournalError
from je_auto_control.utils.action_journal.store import events_from_text
from je_auto_control.utils.codegen.candidate_models import CandidateError, CandidateScript
from je_auto_control.utils.codegen.candidate_validation import validate_candidate_actions
from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.codegen.journal_steps import observed_actions
from je_auto_control.utils.path_guard.policy import scoped_path


def generate_candidate_from_log(path: Path, *, run_id: str, target: str = 'pytest', style: str = 'actions',
                                name: str = 'observed_run', failure_bundle: bool = False) -> CandidateScript:
    """Generate without device calls; validate schema, commands, dry-run and Python AST.

    Only completed replayable leaf actions are included. The source path is
    observed-only and serialized in start order: it never claims original branch,
    loop or parallel semantics. Failed/incomplete/masked steps remain in manifest
    and warnings. A caller must review the result before running it.
    """
    source, content, events = _snapshot(path, run_id)
    actions, steps, warnings = observed_actions(events)
    if not actions:
        raise CandidateError('selected run has no completed replayable leaf actions')
    validation = validate_candidate_actions(actions)
    code = _render(actions, target, style, name, failure_bundle)
    warnings.insert(0, 'Observed path only; serialized in start order. Review before execution; '
                    'branch, loop, retry and parallel semantics are not reconstructed.')
    manifest: Dict[str, JSONValue] = {'schema_version': 1, 'run_id': run_id, 'journal_path': str(source),
                                     'journal_hash': hashlib.sha256(content).hexdigest(),
                                     'target': target, 'style': style, 'observed_path_only': True,
                                     'steps': [dict(step) for step in steps], 'validation': validation}
    validation['python_ast'] = True if target in {'pytest', 'python'} else None
    return CandidateScript('# Observed path only. Source provenance is in the manifest.\n' + code,
                           manifest, tuple(warnings), True, actions)


def _snapshot(path: Path, run_id: str) -> Tuple[Path, bytes, List[ActionEvent]]:
    if not isinstance(run_id, str) or not run_id:
        raise CandidateError('a nonempty selected run_id is required')
    source = scoped_path(path, operation='read')
    try:
        content = source.read_bytes()
        events = events_from_text(content.decode('utf-8'), run_id=run_id)
    except (OSError, UnicodeError) as error:
        raise JournalError('cannot read a complete valid action journal') from error
    if not events:
        raise CandidateError('selected run_id was not found')
    return source, content, events


def _render(actions: List[List[JSONValue]], target: str, style: str, name: str, failure_bundle: bool) -> str:
    try:
        code = generate_code(actions, target=target, name=name, style=style, failure_bundle=failure_bundle)
        if target in {'pytest', 'python'}:
            ast.parse(code)
    except (TypeError, ValueError, SyntaxError) as error:
        raise CandidateError('candidate code generation or syntax validation failed') from error
    return code


__all__ = ['CandidateError', 'CandidateScript', 'generate_candidate_from_log']
