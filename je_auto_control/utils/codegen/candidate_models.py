"""Typed candidate artifacts distinguish observed replay from original control flow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from je_auto_control.utils.action_journal.events import JSONValue, safe_payload
from je_auto_control.utils.exception.exceptions import AutoControlException


class CandidateError(AutoControlException, ValueError):
    """A journal cannot produce a structurally valid, reviewable candidate."""


@dataclass(frozen=True)
class CandidateScript:
    """Generated source, sanitized observed actions and source-step provenance."""
    code: str
    manifest: Dict[str, JSONValue]
    warnings: Tuple[str, ...]
    observed_path_only: bool
    actions: List[List[JSONValue]]

    def to_dict(self) -> Dict[str, JSONValue]:
        """Return an independent finite JSON artifact without object serialization hooks."""
        payload, reasons = safe_payload({'code': self.code, 'manifest': self.manifest,
                                         'warnings': list(self.warnings), 'observed_path_only': self.observed_path_only,
                                         'actions': self.actions})
        if reasons or not isinstance(payload, dict):
            raise CandidateError('candidate artifact must contain finite JSON data')
        return payload
