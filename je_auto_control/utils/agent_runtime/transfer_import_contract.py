"""Closed destination management envelopes carry opaque foreign paths without forwarding local authority."""
from __future__ import annotations

from copy import deepcopy
import time
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import _deadline, _hex, _object, _review_envelope
from je_auto_control.utils.agent_runtime.transfer_records import _text

IMPORT_FIELDS = {
    'review_import': {'source_host', 'export_id', 'target', 'directory', 'idempotency_key'},
    'create_import': {'review', 'note', 'idempotency_key'},
    'get_import': {'import_id'}, 'run_import': {'import_id'}, 'cancel_import': {'import_id'}, 'list_imports': set(),
}
STATES = frozenset({'queued', 'receiving', 'verified', 'published', 'requires_review', 'cancelled', 'expired'})


def import_request(operation: str, request: Mapping) -> dict:
    """Validate exact finite fields; only the destination interprets its directory and registered source label."""
    if not isinstance(operation, str) or operation not in IMPORT_FIELDS:
        raise AgentTaskError('destination transfer management operation is unavailable')
    value = dict(_object(request, IMPORT_FIELDS[operation]))
    if operation == 'review_import':
        _hex(value['export_id'], 32)
        _text(value['idempotency_key'], 256, 'idempotency key')
        for name, limit in (('source_host', 256), ('target', 64), ('directory', 32767)):
            _text(value[name], limit, name)
            if '\x00' in value[name]:
                raise AgentTaskError('destination review contains an invalid text field')
        if value['source_host'] == 'local':
            raise AgentTaskError('destination requires a registered source host')
    elif operation == 'create_import':
        _hex(value['review'], 32)
        _text(value['idempotency_key'], 256, 'idempotency key')
        _text(value['note'], 4000, 'approval note')
    elif operation != 'list_imports':
        _hex(value['import_id'], 32)
    return deepcopy(value)


def import_reply(operation: str, reply: Mapping, request: dict) -> dict:
    """Retain only bounded public receipt fields, never remote issuer, store, origin or cache-account data."""
    if not isinstance(operation, str) or operation not in IMPORT_FIELDS:
        raise AgentTaskError('destination transfer management operation is unavailable')
    if operation == 'review_import':
        return _review(reply, request)
    if operation == 'list_imports':
        values = _object(reply, {'imports'})['imports']
        if not isinstance(values, list) or len(values) > 200:
            raise AgentTaskError('destination import list exceeds its bound')
        return {'imports': [_receipt(item) for item in values]}
    receipt = _receipt(_object(reply, {'import'})['import'])
    if operation != 'create_import' and receipt['import_id'] != request['import_id']:
        raise AgentTaskError('destination import reply changed the requested identity')
    return {'import': receipt}


def _review(reply: Mapping, request: dict) -> dict:
    value, manifest = _review_envelope(reply)
    if manifest.export_id != request['export_id'] or manifest.digest != value['digest']:
        raise AgentTaskError('destination review does not bind the requested source manifest')
    if value['approval_required'] is not True or min(manifest.expires, value['review_expires']) <= time.time():
        raise AgentTaskError('destination import review requires fresh explicit approval')
    return {'review': value['review'], 'digest': manifest.digest, 'manifest': manifest.to_dict(),
            'review_expires': value['review_expires'], 'approval_required': True}


def _receipt(reply: Any) -> dict:
    value = _object(reply, {'import_id', 'state', 'expires', 'manifest_digest', 'files_directory'})
    _hex(value['import_id'], 32)
    _hex(value['manifest_digest'], 64)
    _deadline(value['expires'])
    if not isinstance(value['state'], str) or value['state'] not in STATES:
        raise AgentTaskError('destination import reply contains an invalid public state')
    if value['state'] == 'published':
        _text(value['files_directory'], 32767, 'published files directory')
        if '\x00' in value['files_directory']:
            raise AgentTaskError('destination import reply contains an invalid directory')
    elif value['files_directory'] is not None:
        raise AgentTaskError('unconfirmed destination import cannot expose a files directory')
    return dict(value)
