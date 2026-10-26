"""Convert a fresh registered source proof without borrowing foreign task-read or input authority."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_evidence import resolve_remote_evidence
from je_auto_control.utils.agent_runtime.transfer_models import _canonical


def remote_successor(runtime: Any, batch: dict, node: dict, grant_id: str,
                     binding: dict, deadline: float, owner: Any) -> tuple[dict, list]:
    """Resolve the original coordinator request using its own current registered source account."""
    remaining = deadline - time.monotonic()
    if runtime is None or remaining <= 0:
        raise AgentTaskError('remote completion evidence is unavailable or its review expired')
    with owner.scope():
        proof = resolve_remote_evidence(runtime.transfers.remote, node['host'], batch['hosts'][node['host']],
                                       grant_id, binding, min(5, remaining))
    if time.monotonic() >= deadline:
        raise AgentTaskError('remote completion evidence review expired')
    candidate = {'task_id': proof['task_id'], 'state': 'succeeded', 'verification': proof['verification'],
        'metadata': {'completion_contract': 1, 'input_released': True, 'evidence_handoff': {
            'contract': 1, 'id': proof['grant_id'], 'review': sha256(_canonical(proof)).hexdigest()}}}
    return candidate, deepcopy(proof['chain'])
