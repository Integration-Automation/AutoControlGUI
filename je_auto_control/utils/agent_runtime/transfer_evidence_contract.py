"""Closed portable completion envelopes carry hashes and finite verification, never local authority."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import MAX_MANIFEST_BYTES, _canonical, _deadline, _hex, _object
from je_auto_control.utils.agent_runtime.transfer_records import _text

EVIDENCE_FIELDS = {'review_evidence': {'source_task', 'task_id', 'recipient_policy', 'idempotency_key'},
                   'create_evidence': {'review', 'note', 'idempotency_key'}, 'get_evidence': {'grant_id'},
                   'revoke_evidence': {'grant_id'}, 'list_evidence': {'source_task'}}
_BASE = {'contract', 'grant_id', 'source_task', 'task_id', 'source_snapshot', 'completion_snapshot',
         'submitted_spec_digest', 'chain', 'verification', 'expires', 'evidence_only', 'input_authorized'}
_BINDING = {'source_task', 'request_key_hash', 'submitted_spec_digest'}
_NODE = {'batch_id', 'graph_hash', 'node_id'}


def evidence_binding(value: Mapping) -> dict:
    """Require the exact original accepted key/spec and optional actual DAG identity."""
    if not isinstance(value, Mapping):
        raise AgentTaskError('portable evidence binding must be an object')
    result = dict(_object(value, _BINDING | (_NODE if 'batch_id' in value else set())))
    _hex(result['source_task'], 32)
    for name in ('request_key_hash', 'submitted_spec_digest'):
        _hex(result[name], 64)
    if 'batch_id' in result:
        _node(result, projection=False)
    return result


def _node(value: Mapping, *, projection: bool) -> None:
    _hex(value['batch_id'], 32)
    _hex(value['graph_hash'], 64)
    _text(value['node_id'], 256, 'node identity')
    if projection:
        _hex(value['request_digest'], 64)


def request_digest(binding: Mapping) -> str:
    """Hash only the key and accepted specification actually received by the source."""
    return sha256(_canonical({'key_hash': binding['request_key_hash'],
                              'submitted_spec_digest': binding['submitted_spec_digest']})).hexdigest()


def portable_evidence(value: Mapping, *, resolved: bool = True) -> dict:
    """Validate a bounded redacted proof; a validated DTO alone supplies no current source authority."""
    if not isinstance(value, Mapping):
        raise AgentTaskError('portable evidence must be an object')
    result = dict(_object(value, _BASE | ({'node'} if 'node' in value else set())))
    _flags(result)
    for name in ('grant_id', 'source_task', 'task_id'):
        _hex(result[name], 32)
    for name in ('source_snapshot', 'completion_snapshot', 'submitted_spec_digest'):
        _hex(result[name], 64)
    _deadline(result['expires'])
    _chain(result)
    _reports(result['verification'])
    if 'node' in result:
        _object(result['node'], _NODE | ({'request_digest'} if resolved else set()))
        _node(result['node'], projection=resolved)
    if len(_canonical(result)) > MAX_MANIFEST_BYTES:
        raise AgentTaskError('portable evidence exceeds its finite wire budget')
    return deepcopy(result)


def _flags(value: dict) -> None:
    contract = value['contract']
    if (not isinstance(contract, int) or isinstance(contract, bool) or contract != 1 or
            value['evidence_only'] is not True or value['input_authorized'] is not False):
        raise AgentTaskError('portable evidence requires the exact evidence-only contract')


def _reports(reports: list) -> None:
    if not isinstance(reports, list) or not reports:
        raise AgentTaskError('portable evidence requires independent finite verification')
    for report in reports:
        _object(report, {'kind', 'status'})
        _text(report['kind'], 256, 'criterion kind')
        if report['status'] != 'passed':
            raise AgentTaskError('portable evidence contains an unconfirmed criterion')


def _chain(value: dict) -> None:
    chain = value['chain']
    if not isinstance(chain, list) or not 1 <= len(chain) <= 16:
        raise AgentTaskError('portable evidence requires one to sixteen real recovery links')
    seen, source, snapshot = {value['source_task']}, value['source_task'], value['source_snapshot']
    for link in chain:
        _link(link)
        if link['source_task'] != source or link['task_id'] in seen or link['source_snapshot'] != snapshot:
            raise AgentTaskError('portable evidence chain is discontinuous or cyclic')
        seen.add(link['task_id'])
        source, snapshot = link['task_id'], link['snapshot']
    if source != value['task_id'] or chain[0]['source_snapshot'] != value['source_snapshot']:
        raise AgentTaskError('portable evidence chain changed its original source or final task')
    if chain[-1]['completion_snapshot'] != value['completion_snapshot']:
        raise AgentTaskError('portable evidence chain changed its final completion witness')


def _link(value: Mapping) -> None:
    _object(value, {'source_task', 'task_id', 'source_snapshot', 'snapshot', 'completion_snapshot'})
    for name in ('source_task', 'task_id'):
        _hex(value[name], 32)
    for name in ('source_snapshot', 'snapshot', 'completion_snapshot'):
        _hex(value[name], 64)
