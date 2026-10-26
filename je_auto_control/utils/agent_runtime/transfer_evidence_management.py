"""Closed management projections validate portable evidence consent without importing foreign authority."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import time
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_evidence_contract import EVIDENCE_FIELDS, portable_evidence
from je_auto_control.utils.agent_runtime.transfer_models import _canonical, _deadline, _hex, _object
from je_auto_control.utils.agent_runtime.transfer_records import _text


def evidence_digest(summary: Mapping) -> str:
    """Hash only the exact unresolved public summary approved by the actual source service."""
    return sha256(_canonical(portable_evidence(summary, resolved=False))).hexdigest()


def evidence_request(operation: str, request: Mapping) -> dict:
    """Accept finite source-local identities and explicit consent fields, never caller-supplied principals."""
    value = dict(_object(request, EVIDENCE_FIELDS[operation]))
    if operation == 'review_evidence':
        _hex(value['source_task'], 32)
        _hex(value['task_id'], 32)
        _text(value['idempotency_key'], 256, 'idempotency key')
        if value['recipient_policy'] not in ('caller', 'source_owner'):
            raise AgentTaskError('evidence recipient must derive an actual source-local identity')
    elif operation == 'create_evidence':
        _hex(value['review'], 32)
        _text(value['idempotency_key'], 256, 'idempotency key')
        _text(value['note'], 4000, 'approval note')
    else:
        _hex(value['source_task'] if operation == 'list_evidence' else value['grant_id'], 32)
    return deepcopy(value)


def evidence_reply(operation: str, reply: Mapping, request: dict) -> dict:
    """Check closed management envelopes independently of authenticated evidence resolution and input."""
    if operation == 'review_evidence':
        return _review(reply, request)
    if operation == 'list_evidence':
        return _listing(reply, request['source_task'])
    record = _record(_object(reply, {'evidence'})['evidence'])
    if operation != 'create_evidence' and record['grant_id'] != request['grant_id']:
        raise AgentTaskError('evidence reply changed its requested grant identity')
    expected = {'create_evidence': 'active', 'revoke_evidence': 'revoked'}.get(operation)
    if expected is not None and record['state'] != expected:
        raise AgentTaskError('evidence reply does not confirm the requested management operation')
    return {'evidence': record}


def _review(reply: Mapping, request: dict) -> dict:
    value = _object(reply, {'review', 'digest', 'evidence', 'review_expires', 'approval_required'})
    _hex(value['review'], 32)
    _hex(value['digest'], 64)
    _deadline(value['review_expires'])
    summary = portable_evidence(value['evidence'], resolved=False)
    if (summary['source_task'] != request['source_task'] or summary['task_id'] != request['task_id']
            or evidence_digest(summary) != value['digest'] or value['approval_required'] is not True
            or min(value['review_expires'], summary['expires']) <= time.time()):
        raise AgentTaskError('evidence review does not bind fresh explicit consent for the requested completion')
    return {'review': value['review'], 'digest': value['digest'], 'evidence': summary,
            'review_expires': value['review_expires'], 'approval_required': True}


def _record(reply: Any) -> dict:
    value = _object(reply, {'grant_id', 'state', 'summary'})
    _hex(value['grant_id'], 32)
    summary = portable_evidence(value['summary'], resolved=False)
    state = value['state']
    if (not isinstance(state, str) or state not in {'active', 'expired', 'revoked'}
            or summary['grant_id'] != value['grant_id']):
        raise AgentTaskError('evidence management record has an invalid identity or public state')
    return {'grant_id': value['grant_id'], 'state': state, 'summary': summary}


def _listing(reply: Mapping, source_task: str) -> dict:
    values = _object(reply, {'evidence'})['evidence']
    if not isinstance(values, list) or len(values) > 200:
        raise AgentTaskError('evidence management list exceeds its finite quota')
    records = [_record(value) for value in values]
    if any(value['summary']['source_task'] != source_task for value in records):
        raise AgentTaskError('evidence management list contains an unrelated source')
    return {'evidence': records}
