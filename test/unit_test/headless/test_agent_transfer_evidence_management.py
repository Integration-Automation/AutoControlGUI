"""Closed routed evidence management validates identities, freshness and explicit consent separately from reads."""
from copy import deepcopy
from hashlib import sha256
import time

import pytest

from headless.test_agent_transfer_evidence_contract import projection
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import _canonical
from je_auto_control.utils.agent_runtime.transfer_transport import TransferPeer


def envelope(operation):
    summary = projection()
    summary['expires'] = time.time() + 300
    if operation == 'review_evidence':
        request = {'source_task': summary['source_task'], 'task_id': summary['task_id'],
                   'recipient_policy': 'source_owner', 'idempotency_key': 'routed-evidence'}
        reply = {'review': 'd' * 32, 'digest': sha256(_canonical(summary)).hexdigest(), 'evidence': summary,
                 'review_expires': time.time() + 60, 'approval_required': True}
    elif operation == 'create_evidence':
        request = {'review': 'd' * 32, 'note': 'Reviewed real completion only', 'idempotency_key': 'routed-evidence'}
        reply = {'evidence': {'grant_id': summary['grant_id'], 'state': 'active', 'summary': summary}}
    elif operation == 'list_evidence':
        request = {'source_task': summary['source_task']}
        reply = {'evidence': [{'grant_id': summary['grant_id'], 'state': 'active', 'summary': summary}]}
    else:
        request = {'grant_id': summary['grant_id']}
        reply = {'evidence': {'grant_id': summary['grant_id'],
                 'state': 'revoked' if operation == 'revoke_evidence' else 'active', 'summary': summary}}
    return request, reply


@pytest.mark.parametrize('operation', ['review_evidence', 'create_evidence', 'get_evidence',
                                     'revoke_evidence', 'list_evidence'])
def test_all_management_envelopes_roundtrip_closed_public_evidence(operation):
    request, reply = envelope(operation)
    peer = TransferPeer(lambda *_args: deepcopy(reply))
    assert peer.manage('source', 'f' * 64, operation, request, 3) == reply


@pytest.mark.parametrize('change', ['source', 'task', 'digest', 'review', 'review-expiry', 'expiry',
                                   'approval', 'private', 'input', 'resolved-node'])
def test_review_refuses_misbound_expired_private_or_nonconsensual_evidence(change):
    request, reply = envelope('review_evidence')
    if change in {'source', 'task'}:
        request[change + '_task' if change == 'source' else 'task_id'] = '0' * 32
    elif change in {'digest', 'review', 'review-expiry', 'approval'}:
        key, value = {'digest': ('digest', '0' * 64), 'review': ('review', 'not-a-token'),
                      'review-expiry': ('review_expires', time.time() - 1),
                      'approval': ('approval_required', False)}[change]
        reply[key] = value
    else:
        summary = reply['evidence']
        if change == 'expiry':
            summary['expires'] = time.time() - 1
        elif change == 'private':
            summary['owner'] = {'store_path': 'foreign-private.json'}
        elif change == 'input':
            summary['input_authorized'] = True
        else:
            summary['node'] = {'batch_id': '1' * 32, 'graph_hash': '2' * 64, 'node_id': 'node',
                               'request_digest': '3' * 64}
        reply['digest'] = sha256(_canonical(summary)).hexdigest()
    with pytest.raises(AgentTaskError):
        TransferPeer(lambda *_args: reply).manage('source', 'f' * 64, 'review_evidence', request, 3)


@pytest.mark.parametrize('operation,change', [('get_evidence', 'identity'), ('get_evidence', 'summary-id'),
    ('revoke_evidence', 'state'), ('create_evidence', 'state'), ('list_evidence', 'source'),
    ('list_evidence', 'quota'), ('get_evidence', 'private')])
def test_management_records_refuse_wrong_identity_state_quota_and_private_fields(operation, change):
    request, reply = envelope(operation)
    value = reply['evidence'][0] if operation == 'list_evidence' else reply['evidence']
    if change == 'identity':
        request['grant_id'] = '0' * 32
    elif change == 'summary-id':
        value['grant_id'] = '0' * 32
    elif change == 'state':
        value['state'] = 'active' if operation == 'revoke_evidence' else 'revoked'
    elif change == 'source':
        request['source_task'] = '0' * 32
    elif change == 'quota':
        reply['evidence'] *= 201
    else:
        value['issuer'] = 'private'
    with pytest.raises(AgentTaskError):
        TransferPeer(lambda *_args: reply).manage('source', 'f' * 64, operation, request, 3)
