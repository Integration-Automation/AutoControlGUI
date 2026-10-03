"""JSON adapter for journal candidate previews and optional artifact export."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from je_auto_control.utils.action_journal.events import JSONValue
from je_auto_control.utils.codegen.candidate_artifacts import write_candidate_artifacts
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log


def generate_journal_candidate(journal_path: str, run_id: str, target: str = 'pytest', style: str = 'actions',
                               name: str = 'observed_run', failure_bundle: bool = False,
                               output_path: Optional[str] = None) -> Dict[str, JSONValue]:
    """Generate a selected-run candidate without executing it; optionally export three artifacts."""
    candidate = generate_candidate_from_log(Path(journal_path), run_id=run_id, target=target, style=style,
                                            name=name, failure_bundle=failure_bundle)
    result = candidate.to_dict()
    if output_path is not None:
        result['artifacts'] = write_candidate_artifacts(candidate, output_path)
    return result
