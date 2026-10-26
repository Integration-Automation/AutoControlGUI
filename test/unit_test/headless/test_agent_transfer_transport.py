"""Real registered peer reads and bounded validation of malformed injected wire replies."""
import base64
from copy import deepcopy
from hashlib import sha256
import importlib
import importlib.util
import time
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_registered import registered_source, binding
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, transport
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.dag import managed_tasks


def peer_type():
    name = 'je_auto_control.utils.agent_runtime.transfer_transport'
    assert importlib.util.find_spec(name) is not None, 'the neutral TransferPeer validator must exist'
    return importlib.import_module(name).TransferPeer


@pytest.mark.parametrize('named', [False, True])
def test_real_registered_peer_returns_exact_manifest_and_hash_checked_chunk(tmp_path, monkeypatch, named):
    with registered_source(tmp_path, monkeypatch, named=named) as values:
        _server, exported, body, _token, _book, _users = values
        peer = peer_type()(managed_tasks.registered_host_transfer)
        pin = binding()
        manifest = peer.call('source', pin, 'export', {'export_id': exported['export_id']}, 3)
        assert manifest == exported['manifest']
        digest = manifest['files'][0]['chunks'][0]
        chunk = peer.call('source', pin, 'chunk', {'export_id': exported['export_id'], 'sha256': digest}, 3)
        assert chunk == {'contract': 1, 'sha256': digest, 'data': base64.b64encode(body).decode('ascii')}


def manifest_reply():
    body = b'owned peer bytes'
    digest = sha256(body).hexdigest()
    return {'contract': 1, 'export_id': 'a' * 32, 'source_task': 'b' * 32, 'source_snapshot': 'c' * 64,
            'submission_digest': 'd' * 64, 'expires': time.time() + 300,
            'files': [{'name': 'report.txt', 'size': len(body), 'sha256': digest, 'chunks': [digest]}]}


@pytest.mark.parametrize('change', ['wrong_export', 'extra_authority', 'boolean_contract', 'expired'])
def test_malformed_manifest_reply_cannot_become_a_validated_source_descriptor(change):
    reply = manifest_reply()
    if change == 'wrong_export':
        reply['export_id'] = 'e' * 32
    elif change == 'extra_authority':
        reply['principal'] = {'store_path': 'foreign-store'}
    elif change == 'boolean_contract':
        reply['contract'] = True
    else:
        reply['expires'] = time.time() - 1
    peer = peer_type()(lambda *_args: deepcopy(reply))
    with pytest.raises(AgentTaskError):
        peer.call('source', 'f' * 64, 'export', {'export_id': 'a' * 32}, 3)


@pytest.mark.parametrize('change', ['bad_base64', 'wrong_bytes', 'wrong_hash', 'boolean_contract',
                                   'empty', 'oversized', 'noncanonical_padding'])
def test_chunk_reply_requires_exact_hash_bounded_bytes_and_canonical_base64(change):
    body = b'f'
    digest = sha256(body).hexdigest()
    reply = {'contract': 1, 'sha256': digest, 'data': base64.b64encode(body).decode('ascii')}
    if change == 'bad_base64':
        reply['data'] = 'not base64!'
    elif change == 'wrong_bytes':
        reply['data'] = base64.b64encode(b'g').decode('ascii')
    elif change == 'wrong_hash':
        reply['sha256'] = '0' * 64
    elif change == 'boolean_contract':
        reply['contract'] = True
    elif change == 'empty':
        reply['data'] = ''
    elif change == 'oversized':
        reply['data'] = base64.b64encode(b'x' * (256 * 1024 + 1)).decode('ascii')
    else:
        reply['data'] = 'Zh=='
    peer = peer_type()(lambda *_args: deepcopy(reply))
    with pytest.raises(AgentTaskError):
        peer.call('source', 'f' * 64, 'chunk', {'export_id': 'a' * 32, 'sha256': digest}, 3)


@pytest.mark.parametrize('operation,payload', [('evidence', {'export_id': 'a' * 32}),
    ('chunk', {'export_id': 'a' * 32}), ('export', {'export_id': 'a' * 32, 'principal': {}}),
    ('export', {'export_id': '../source'})])
def test_unavailable_or_invalid_peer_request_fails_before_the_host_adapter(operation, payload):
    def forbidden(*_args):
        raise AssertionError('invalid peer request reached the host adapter')
    with pytest.raises(AgentTaskError):
        peer_type()(forbidden).call('source', 'f' * 64, operation, payload, 3)


def test_late_injected_wire_reply_is_discarded_even_when_its_manifest_is_well_formed(monkeypatch):
    peer = peer_type()
    module = importlib.import_module(peer.__module__)
    clock = [0.0]
    reply = manifest_reply()
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0], time=time.time))
    def late(*_args):
        clock[0] = 4.0
        return reply
    with pytest.raises(AgentTaskError, match='deadline'):
        peer(late).call('source', 'f' * 64, 'export', {'export_id': 'a' * 32}, 3)


def test_runtime_owned_peer_uses_its_actual_batch_host_adapter_over_real_http(tmp_path, monkeypatch):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, exported, _body, _token, _book, _users = values
        runtime = AgentRuntime(tmp_path / 'coordinator.sqlite3', targets={'local-files': FileTarget()})
        try:
            peer = runtime.transfers.remote
            assert isinstance(peer, peer_type()), 'runtime must own the injected registered peer'
            pin = runtime.batches.transfer_binding('source')
            manifest = peer.call('source', pin, 'export', {'export_id': exported['export_id']}, 3)
            assert manifest == exported['manifest']
        finally:
            runtime.close()


def test_retained_peer_refuses_a_closed_runtime_before_host_lookup_or_network(tmp_path, monkeypatch):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, exported, _body, _token, _book, _users = values
        runtime = AgentRuntime(tmp_path / 'coordinator.sqlite3', targets={'local-files': FileTarget()})
        try:
            peer = runtime.transfers.remote
            assert isinstance(peer, peer_type()), 'runtime must own the injected registered peer'
            pin = runtime.batches.transfer_binding('source')
            runtime.close()
            def forbidden(*_args, **_kwargs):
                raise AssertionError('a closed runtime dispatched a registered request')
            monkeypatch.setattr(transport, 'request_json', forbidden)
            with pytest.raises(AgentTaskError, match='closed'):
                peer.call('source', pin, 'export', {'export_id': exported['export_id']}, 3)
        finally:
            runtime.close()


@pytest.mark.parametrize('timeout', [True, 0, -1, float('nan'), float('inf'), 31, '3',
                                   pytest.param(1 << 4096, id='huge-integer')])
def test_invalid_peer_timeout_fails_with_typed_error_before_the_adapter(timeout):
    def forbidden(*_args):
        raise AssertionError('invalid timeout reached the adapter')
    with pytest.raises(AgentTaskError):
        peer_type()(forbidden).call('source', 'f' * 64, 'export', {'export_id': 'a' * 32}, timeout)
