"""Compare sanitized current actions with a journal candidate for review."""
from __future__ import annotations

import difflib
import json

from je_auto_control.utils.action_journal.events import safe_payload
from je_auto_control.utils.codegen.candidate_models import CandidateScript
from je_auto_control.utils.executor.action_redaction import redact_actions


def candidate_action_diff(candidate: CandidateScript, current: object) -> str:
    """Return a unified data diff without executing actions or exposing current literals."""
    copied, _ = safe_payload(current)
    before = json.dumps(redact_actions(copied), ensure_ascii=False, allow_nan=False, indent=2).splitlines()
    after = json.dumps(candidate.to_dict()['actions'], ensure_ascii=False, allow_nan=False, indent=2).splitlines()
    return '\n'.join(difflib.unified_diff(before, after, fromfile='current', tofile='observed', lineterm=''))
