"""Real authenticated loopback reads keep source authority and private delegation boundaries separate."""
import base64
from contextlib import contextmanager
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from headless.test_agent_transfer_source import completed_source
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.delegation import HEADER, sign_principal
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.rest_api.rest_auth import RestAuthGate


@contextmanager
def source_server(tmp_path, *, named=False, local_bridge=False):
    with completed_source(tmp_path, named=named) as (runtime, task, _output, body, users):
        server = RestApiServer(port=0, token='owned-source-service', user_store=None if local_bridge else users,
                               agent_runtime=runtime, enable_audit=False, use_environment_users=False)
        server.start()
        try:
            yield server, task, body, users
        finally:
            server.stop()


def post(server, path, payload, *, token=None, headers=None, raw=None):
    address = urlsplit(server.base_url)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=3)
    body = json.dumps(payload).encode() if raw is None else raw
    fields = {'Authorization': 'Bearer ' + (server.token if token is None else token),
              'Content-Type': 'application/json', **(headers or {})}
    try:
        connection.request('POST', path, body=body, headers=fields)
        reply = connection.getresponse()
        return reply.status, json.loads(reply.read())
    finally:
        connection.close()


def approved_export(server, task, *, token=None, selection=None):
    status, review = post(server, '/agent/transfer', {'operation': 'review_export', 'request': {
        'source_task': task, 'selection': [{'criterion': 0, 'names': []}] if selection is None else selection,
        'recipient_policy': 'caller', 'idempotency_key': 'http-reviewed-export'}}, token=token)
    assert status == 200, review
    status, created = post(server, '/agent/transfer', {'operation': 'create_export', 'request': {
        'review': review['review'], 'note': 'Approve only these exact source bytes',
        'idempotency_key': 'http-reviewed-export'}}, token=token)
    assert status == 200, created
    return created['export']


def test_authenticated_http_exports_exact_reviewed_bytes_without_local_delegation(tmp_path):
    with source_server(tmp_path) as (server, task, body, _users):
        exported = approved_export(server, task)
        status, manifest = post(server, '/agent/transfer/peer', {'operation': 'export',
            'request': {'export_id': exported['export_id']}})
        assert status == 200
        assert manifest == exported['manifest']
        assert str(tmp_path) not in json.dumps(manifest)
        digest = manifest['files'][0]['chunks'][0]
        status, chunk = post(server, '/agent/transfer/peer', {'operation': 'chunk',
            'request': {'export_id': exported['export_id'], 'sha256': digest}})
        assert status == 200
        assert chunk == {'contract': 1, 'sha256': digest, 'data': base64.b64encode(body).decode('ascii')}
        status, _reply = post(server, '/agent/transfer/peer', {'operation': 'chunk',
            'request': {'export_id': exported['export_id'], 'sha256': '0' * 64}})
        assert status == 409


def test_named_peer_uses_receiving_store_recipient_and_current_role(tmp_path):
    with source_server(tmp_path, named=True) as (server, task, _body, users):
        owner, other = users.rotate_token('owner'), users.rotate_token('other')
        exported = approved_export(server, task, token=owner)
        payload = {'operation': 'export', 'request': {'export_id': exported['export_id']}}
        assert post(server, '/agent/transfer/peer', payload, token=owner)[0] == 200
        assert post(server, '/agent/transfer/peer', payload, token=other)[0] == 409
        assert post(server, '/agent/transfer/peer', payload, token='wrong-source-credential')[0] == 401
        users.set_role('owner', 'viewer')
        assert post(server, '/agent/transfer/peer', payload, token=owner)[0] == 403


def test_local_service_transfer_preserves_real_store_backed_owner_delegation(tmp_path):
    with source_server(tmp_path, named=True, local_bridge=True) as (server, task, _body, users):
        metadata = tmp_path / 'owned-client.json'
        metadata.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        client = AgentRuntimeClient(metadata)
        owner = AuthorizationContext('owner', 'operator', store_path=str(users.path))
        with authorization_scope(owner):
            review = client.call('transfer', {'operation': 'review_export', 'request': {
                'source_task': task, 'selection': [{'criterion': 0, 'names': []}],
                'recipient_policy': 'caller', 'idempotency_key': 'local-owner-export'}})
            created = client.call('transfer', {'operation': 'create_export', 'request': {
                'review': review['review'], 'note': 'Approve the actual named local owner output',
                'idempotency_key': 'local-owner-export'}})['export']
            assert client.call('transfer', {'operation': 'get_export', 'request': {
                'export_id': created['export_id']}})['export'] == created
        # The shared peer credential does not acquire the forwarded local owner's identity.
        assert post(server, '/agent/transfer/peer', {'operation': 'export', 'request': {
            'export_id': created['export_id']}})[0] == 409


@pytest.mark.parametrize('kind', ['empty_principal', 'foreign_principal', 'empty_origin', 'origin'])
def test_peer_refuses_private_header_presence_before_foreign_store_lookup(tmp_path, monkeypatch, kind):
    from je_auto_control.utils.rbac import deferred
    with source_server(tmp_path) as (server, _task, _body, _users):
        foreign = tmp_path / 'foreign-users.json'
        loads = []
        actual_store = deferred.UserStore

        def guarded_store(path):
            if Path(path) == foreign:
                loads.append(path)
                raise AuthorizationError('foreign store must not be consulted by a peer request')
            return actual_store(path)

        monkeypatch.setattr(deferred, 'UserStore', guarded_store)
        forged = sign_principal(AuthorizationContext('outside', 'admin', store_path=str(foreign)),
                                server.token, '/agent/transfer/peer')
        headers = {'empty_principal': {HEADER: ''}, 'foreign_principal': {HEADER: forged},
                   'empty_origin': {'X-AutoControl-Agent-Origin': ''},
                   'origin': {'X-AutoControl-Agent-Origin': 'a' * 32}}[kind]
        status, _reply = post(server, '/agent/transfer/peer', {'operation': 'export',
            'request': {'export_id': '0' * 32}}, headers=headers)
        assert status == 401
        assert loads == []
        assert not foreign.exists()


def test_private_header_refusal_keeps_the_existing_receiving_auth_rate_limit(tmp_path):
    with source_server(tmp_path) as (server, _task, _body, _users):
        server._server.auth_gate = RestAuthGate(server.token, requests_per_minute=0, burst=1)
        payload = {'operation': 'export', 'request': {'export_id': '0' * 32}}
        assert post(server, '/agent/transfer/peer', payload, headers={HEADER: ''})[0] == 401
        assert post(server, '/agent/transfer/peer', payload)[0] == 429


def test_peer_accepts_one_mib_body_but_refuses_larger_before_reading_it(tmp_path):
    with source_server(tmp_path) as (server, task, _body, _users):
        exported = approved_export(server, task)
        payload = {'operation': 'export', 'request': {'export_id': exported['export_id']}}
        encoded = json.dumps(payload).encode()
        raw = encoded + b' ' * (1024 * 1024 - len(encoded))
        status, manifest = post(server, '/agent/transfer/peer', payload, raw=raw)
        assert status == 200
        assert manifest == exported['manifest']
        address = urlsplit(server.base_url)
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=3)
        try:
            connection.putrequest('POST', '/agent/transfer/peer')
            connection.putheader('Authorization', 'Bearer ' + server.token)
            connection.putheader('Content-Length', str(1024 * 1024 + 1))
            connection.endheaders()
            reply = connection.getresponse()
            assert reply.status == 413
            assert 'error' in json.loads(reply.read())
        finally:
            connection.close()
