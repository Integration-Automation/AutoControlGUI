"""Destination DTO tests validate wire shape only; fixtures do not assert any real task completion."""
from copy import deepcopy

import pytest

from headless.test_agent_transfer_management import reviewed_reply
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_import_contract import import_request, import_reply
from je_auto_control.utils.agent_runtime.transfer_transport import TransferPeer


def request():
    return {'source_host': 'source', 'export_id': 'a' * 32, 'target': 'files',
            'directory': '/interpreted-only-by-destination', 'idempotency_key': 'reviewed-import'}


@pytest.mark.parametrize('operation', [None, True, [], {}, 'shell'])
def test_unknown_destination_operations_are_typed_boundary_errors(operation):
    with pytest.raises(AgentTaskError):
        import_request(operation, {})
    with pytest.raises(AgentTaskError):
        import_reply(operation, {}, {})


@pytest.mark.parametrize('field,value', [('source_host', []), ('source_host', 'local'), ('export_id', True),
    ('target', None), ('directory', '\x00'), ('directory', 'x' * 32768), ('idempotency_key', ''),
    ('principal', {'user_id': 'forged'}), ('account', 'f' * 32), ('origin', 'a' * 32)],
    ids=['source-type', 'source-local', 'export-id', 'target', 'nul-path', 'long-path',
         'key', 'principal', 'account', 'origin'])
def test_invalid_destination_request_never_reaches_an_adapter(field, value):
    calls = []
    peer = TransferPeer(lambda *_args: calls.append(True))
    with pytest.raises(AgentTaskError):
        peer.manage('destination', 'f' * 64, 'review_import', {**request(), field: value}, 3)
    assert calls == []


@pytest.mark.parametrize('change', ['private', 'identity', 'digest', 'approval', 'contract', 'expiry'])
def test_destination_review_reply_is_closed_and_binds_the_requested_export(change):
    reply = reviewed_reply()
    if change == 'private':
        reply['issuer'] = {'user_id': 'foreign'}
    elif change == 'identity':
        reply['manifest']['export_id'] = 'f' * 32
    elif change == 'digest':
        reply['digest'] = 'f' * 64
    elif change == 'approval':
        reply['approval_required'] = 1
    elif change == 'contract':
        reply['manifest']['contract'] = True
    else:
        reply['review_expires'] = False
    peer = TransferPeer(lambda *_args: deepcopy(reply))
    with pytest.raises(AgentTaskError):
        peer.manage('destination', 'f' * 64, 'review_import', request(), 3)


@pytest.mark.parametrize('field,value', [('import_id', 'wrong'), ('state', True), ('expires', True),
    ('manifest_digest', 'wrong'), ('files_directory', '/not-confirmed'), ('issuer', {'user_id': 'foreign'})])
def test_destination_receipt_rejects_private_or_unconfirmed_fields(field, value):
    receipt = {'import_id': 'a' * 32, 'state': 'queued', 'expires': 10**10,
               'manifest_digest': 'b' * 64, 'files_directory': None}
    with pytest.raises(AgentTaskError):
        import_reply('get_import', {'import': {**receipt, field: value}}, {'import_id': 'a' * 32})


def test_confirmed_foreign_path_is_opaque_data_and_requires_an_exact_requested_id():
    receipt = {'import_id': 'a' * 32, 'state': 'published', 'expires': 10**10,
               'manifest_digest': 'b' * 64, 'files_directory': 'Z:\\destination-only\\generation\\files'}
    assert import_reply('get_import', {'import': receipt}, {'import_id': 'a' * 32}) == {'import': receipt}
    with pytest.raises(AgentTaskError):
        import_reply('get_import', {'import': receipt}, {'import_id': 'f' * 32})
