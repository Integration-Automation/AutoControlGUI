"""Write reviewed candidate source and provenance with checked derived paths."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Union

from je_auto_control.utils.action_journal.events import JSONValue
from je_auto_control.utils.codegen.candidate_models import CandidateError, CandidateScript
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.path_guard.policy import scoped_path


def write_candidate_artifacts(candidate: CandidateScript, output: Union[str, Path]) -> Dict[str, JSONValue]:
    """Save source, manifest and actions without overwriting the input journal."""
    destination = scoped_path(output, operation='write')
    manifest = scoped_path(destination.with_suffix('.manifest.json'), operation='write')
    actions = scoped_path(destination.with_suffix('.actions.json'), operation='write')
    source = candidate.manifest.get('journal_path')
    if not isinstance(source, str) or scoped_path(source, operation='read') in {destination, manifest, actions}:
        raise CandidateError('candidate artifacts cannot replace their source journal')
    payload = candidate.to_dict()
    try:
        scoped_path(destination.parent, operation='write').mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, candidate.code)
        atomic_write_text(manifest, json.dumps(payload['manifest'], ensure_ascii=False, allow_nan=False, indent=2))
        atomic_write_text(actions, json.dumps(payload['actions'], ensure_ascii=False, allow_nan=False, indent=2))
    except OSError as error:
        raise CandidateError('cannot write candidate artifacts') from error
    return {'code_path': str(destination), 'manifest_path': str(manifest), 'actions_path': str(actions)}
