"""Adversarial wire DTOs cannot turn flags, paths or inconsistent chains into portable authority."""
from copy import deepcopy
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_evidence_contract import evidence_binding, portable_evidence
from je_auto_control.utils.agent_runtime.transfer_transport import TransferPeer


def projection():
    return {'contract': 1, 'grant_id': 'a' * 32, 'source_task': 'b' * 32, 'task_id': 'c' * 32,
        'source_snapshot': 'd' * 64, 'completion_snapshot': 'e' * 64, 'submitted_spec_digest': 'f' * 64,
        'chain': [{'source_task': 'b' * 32, 'task_id': 'c' * 32, 'source_snapshot': 'd' * 64,
                   'snapshot': '1' * 64, 'completion_snapshot': 'e' * 64}],
        'verification': [{'kind': 'actions_complete', 'status': 'passed'}], 'expires': 2000.0,
        'evidence_only': True, 'input_authorized': False}


@pytest.mark.parametrize('change', ['bool-version', 'float-version', 'input', 'expiry', 'private', 'chain-source',
                                   'chain-completion', 'chain-empty', 'criterion', 'raw-result'])
def test_portable_evidence_rejects_nonexact_or_private_completion_fields(change):
    value = projection()
    mutations = {'bool-version': {'contract': True}, 'float-version': {'contract': 1.0},
        'input': {'input_authorized': True}, 'expiry': {'expires': float('nan')},
        'private': {'owner': {'store_path': 'foreign-users.json'}}, 'chain-empty': {'chain': []},
        'raw-result': {'verification': [{'kind': 'actions_complete', 'status': 'passed', 'value': 'private'}]}}
    value.update(mutations.get(change, {}))
    if change == 'chain-source':
        value['chain'][0]['source_snapshot'] = '0' * 64
    elif change == 'chain-completion':
        value['chain'][0]['completion_snapshot'] = '0' * 64
    elif change == 'criterion':
        value['verification'][0]['status'] = 'unknown'
    with pytest.raises(AgentTaskError):
        portable_evidence(value)


@pytest.mark.parametrize('value', [None, True, [], 1, 'source'])
def test_portable_binding_and_projection_refuse_nonobjects_with_typed_errors(value):
    for validate in (portable_evidence, evidence_binding):
        with pytest.raises(AgentTaskError):
            validate(value)


def test_portable_chain_checks_the_actual_intermediate_snapshot_and_returns_detached_values():
    value = projection()
    value['chain'].append({'source_task': 'c' * 32, 'task_id': '2' * 32, 'source_snapshot': '1' * 64,
                          'snapshot': '3' * 64, 'completion_snapshot': '4' * 64})
    value.update(task_id='2' * 32, completion_snapshot='4' * 64)
    assert portable_evidence(value) == value
    broken = deepcopy(value)
    broken['chain'][1]['source_snapshot'] = '0' * 64
    with pytest.raises(AgentTaskError):
        portable_evidence(broken)
    result = portable_evidence(value)
    result['chain'].clear()
    assert len(value['chain']) == 2


@pytest.mark.parametrize('change', ['grant', 'source', 'spec', 'expiry', 'flags'])
def test_transfer_peer_refuses_an_expired_or_misbound_authenticated_reply(change):
    value = projection()
    value['expires'] = time.time() + 60
    binding = {'source_task': value['source_task'], 'request_key_hash': '9' * 64,
               'submitted_spec_digest': value['submitted_spec_digest']}
    request = {'grant_id': value['grant_id'], 'binding': binding}
    if change == 'grant':
        value['grant_id'] = '0' * 32
    elif change == 'source':
        value['source_task'] = '0' * 32
    elif change == 'spec':
        value['submitted_spec_digest'] = '0' * 64
    elif change == 'expiry':
        value['expires'] = time.time() - 1
    else:
        value['input_authorized'] = True
    peer = TransferPeer(lambda *_args: value)
    with pytest.raises(AgentTaskError):
        peer.call('source', '8' * 64, 'evidence', request, 3)
