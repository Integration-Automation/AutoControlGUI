"""Closed source management envelopes validate foreign replies before local consent can retain them."""
from __future__ import annotations

from copy import deepcopy
import time
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import (
    TransferManifest, TransferSelection, _deadline, _hex, _object,
)
from je_auto_control.utils.agent_runtime.transfer_records import _text

SOURCE_FIELDS = {'review_export': {'source_task', 'selection', 'recipient_policy', 'idempotency_key'},
                 'create_export': {'review', 'note', 'idempotency_key'}, 'get_export': {'export_id'},
                 'revoke_export': {'export_id'}, 'list_exports': {'source_task'}}


def management_request(operation: str, request: Mapping[str, Any]) -> dict:
    """Accept only the finite source operation's exact public fields, never a host or private principal."""
    if not isinstance(operation, str) or operation not in SOURCE_FIELDS:
        raise AgentTaskError('source transfer management operation is unavailable')
    value = dict(_object(request, SOURCE_FIELDS[operation]))
    if operation == 'review_export':
        _review_request(value)
    elif operation == 'create_export':
        _hex(value['review'], 32)
        _text(value['note'], 4000, 'approval note')
        _text(value['idempotency_key'], 256, 'idempotency key')
    else:
        _hex(value['source_task'] if operation == 'list_exports' else value['export_id'], 32)
    return deepcopy(value)


def _review_request(value: dict) -> None:
    _hex(value['source_task'], 32)
    _text(value['idempotency_key'], 256, 'idempotency key')
    if value['recipient_policy'] not in ('caller', 'source_owner'):
        raise AgentTaskError('recipient policy must select an actual source-local identity')
    if not isinstance(value['selection'], list) or not 1 <= len(value['selection']) <= 500:
        raise AgentTaskError('source review requires one to five hundred criterion selections')
    for item in value['selection']:
        TransferSelection.from_dict(item)


def management_reply(operation: str, reply: Mapping[str, Any], request: dict) -> dict:
    """Validate exact bounded public projections without granting source-task visibility or input authority."""
    if operation == 'review_export':
        return _review_reply(reply, request)
    if operation == 'list_exports':
        return _list_reply(reply, request['source_task'])
    value = _export(_object(reply, {'export'})['export'])
    if operation in {'get_export', 'revoke_export'} and value['export_id'] != request['export_id']:
        raise AgentTaskError('source export reply changed its requested identity')
    expected = {'create_export': 'active', 'revoke_export': 'revoked'}.get(operation)
    if expected is not None and value['state'] != expected:
        raise AgentTaskError('source export reply does not confirm the requested operation')
    return {'export': value}


def _list_reply(reply: Mapping[str, Any], source_task: str) -> dict:
    value = _object(reply, {'exports'})['exports']
    if not isinstance(value, list) or len(value) > 128:
        raise AgentTaskError('source export list exceeds its finite grant quota')
    exports = [_export(item) for item in value]
    if any(item['manifest']['source_task'] != source_task for item in exports):
        raise AgentTaskError('source export list contains an unrelated task')
    return {'exports': exports}


def _review_reply(reply: Mapping[str, Any], request: dict) -> dict:
    value = _object(reply, {'review', 'digest', 'manifest', 'review_expires', 'approval_required'})
    _hex(value['review'], 32)
    _hex(value['digest'], 64)
    _deadline(value['review_expires'])
    manifest = TransferManifest.from_dict(value['manifest'])
    if (manifest.source_task != request['source_task'] or manifest.digest != value['digest']
            or value['approval_required'] is not True or min(value['review_expires'], manifest.expires) <= time.time()):
        raise AgentTaskError('source review reply does not bind fresh explicit consent for the requested task')
    return {'review': value['review'], 'digest': manifest.digest, 'manifest': manifest.to_dict(),
            'review_expires': value['review_expires'], 'approval_required': True}


def _export(reply: Any) -> dict:
    value = _object(reply, {'export_id', 'state', 'manifest', 'cleanup_pending'})
    _hex(value['export_id'], 32)
    manifest = TransferManifest.from_dict(value['manifest'])
    state = value['state']
    if (not isinstance(state, str) or state not in {'active', 'expired', 'revoked', 'requires_review'}
            or not isinstance(value['cleanup_pending'], bool)):
        raise AgentTaskError('source export reply contains an invalid public state')
    if manifest.export_id != value['export_id'] or (value['cleanup_pending'] and state != 'revoked'):
        raise AgentTaskError('source export reply contains an invalid state or immutable identity')
    return {'export_id': value['export_id'], 'state': state, 'manifest': manifest.to_dict(),
            'cleanup_pending': value['cleanup_pending']}
