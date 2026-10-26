"""Closed management DTOs reject malformed foreign replies before routed consent is stored."""
from copy import deepcopy
from hashlib import sha256
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import TransferManifest
from je_auto_control.utils.agent_runtime.transfer_transport import TransferPeer


def source_request():
    return {'source_task': 'b' * 32, 'selection': [{'criterion': 0, 'names': []}],
            'recipient_policy': 'caller', 'idempotency_key': 'actual-reviewed-key'}


def reviewed_reply():
    digest = sha256(b'x').hexdigest()
    manifest = {'contract': 1, 'export_id': 'a' * 32, 'source_task': 'b' * 32,
                'source_snapshot': 'c' * 64, 'submission_digest': 'd' * 64,
                'files': [{'name': 'report.txt', 'sha256': digest, 'size': 1, 'chunks': [digest]}],
                'expires': time.time() + 600}
    return {'review': 'e' * 32, 'digest': TransferManifest.from_dict(manifest).digest, 'manifest': manifest,
            'review_expires': time.time() + 300, 'approval_required': True}


@pytest.mark.parametrize('change', ['unknown', 'digest', 'task', 'boolean_contract', 'expired',
                                  'approval', 'expiry_boolean', 'private_manifest'])
def test_foreign_review_reply_is_exact_typed_and_binds_the_requested_source(change):
    reply = reviewed_reply()
    if change == 'unknown':
        reply['principal'] = {'user_id': 'foreign'}
    elif change == 'digest':
        reply['digest'] = 'f' * 64
    elif change == 'task':
        reply['manifest']['source_task'] = 'f' * 32
        reply['digest'] = TransferManifest.from_dict(reply['manifest']).digest
    elif change == 'boolean_contract':
        reply['manifest']['contract'] = True
    elif change == 'expired':
        reply['review_expires'] = time.time() - 1
    elif change == 'approval':
        reply['approval_required'] = 1
    elif change == 'expiry_boolean':
        reply['review_expires'] = True
    else:
        reply['manifest']['owner'] = {'store_path': 'foreign-private-store'}
    peer = TransferPeer(lambda *_args: deepcopy(reply))
    manage = getattr(peer, 'manage', None)
    assert callable(manage), 'a bounded closed management method must validate replies before routing'
    with pytest.raises(AgentTaskError):
        manage('source', 'f' * 64, 'review_export', source_request(), 3)


def test_valid_closed_management_review_preserves_only_the_exact_public_envelope():
    reply = reviewed_reply()
    peer = TransferPeer(lambda *_args: deepcopy(reply))
    manage = getattr(peer, 'manage', None)
    assert callable(manage)
    assert manage('source', 'f' * 64, 'review_export', source_request(), 3) == reply


@pytest.mark.parametrize('change', ['unknown', 'cleanup_type', 'cleanup_state', 'identity', 'unconfirmed'])
def test_foreign_creation_ack_is_a_closed_confirmed_public_export(change):
    value = reviewed_reply()
    exported = {'export_id': value['manifest']['export_id'], 'state': 'active',
                'manifest': value['manifest'], 'cleanup_pending': False}
    if change == 'unknown':
        exported['owner'] = {'user_id': 'foreign'}
    elif change == 'cleanup_type':
        exported['cleanup_pending'] = 0
    elif change == 'cleanup_state':
        exported['cleanup_pending'] = True
    elif change == 'identity':
        exported['export_id'] = 'f' * 32
    else:
        exported['state'] = 'requires_review'
    peer = TransferPeer(lambda *_args: {'export': deepcopy(exported)})
    with pytest.raises(AgentTaskError):
        peer.manage('source', 'f' * 64, 'create_export', {'review': value['review'],
            'note': 'Approve the selected bytes', 'idempotency_key': 'exact-created-export'}, 3)
