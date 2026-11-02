"""Registered transfer transport uses current persisted configuration and receiving-host credentials."""
from contextlib import contextmanager
import json
import subprocess
import sys

import pytest

from headless.test_agent_transfer_peer_security import source_server, approved_export
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentTaskError, origin_policy, transport
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@contextmanager
def registered_source(tmp_path, monkeypatch, *, named=True):
    source_root = tmp_path / 'source'
    source_root.mkdir()
    users = UserStore(tmp_path / 'coordinator-users.json')
    users.add_user(user_id='coordinator', display_name='Coordinator', role='admin')
    actor = AuthorizationContext('coordinator', 'admin', store_path=str(users.path))
    with source_server(source_root, named=named) as (server, task, body, source_users):
        token = source_users.rotate_token('owner') if named else server.token
        book = admin_client.AdminConsoleClient(persist_path=tmp_path / 'hosts.json')
        book.add_host('source', server.base_url, token)
        monkeypatch.setattr(admin_client, '_default_console', book)
        exported = approved_export(server, task, token=token)
        with authorization_scope(actor):
            yield server, exported, body, token, book, users


def adapter():
    value = getattr(managed_tasks, 'registered_host_transfer', None)
    assert callable(value), 'registered_host_transfer must provide the actual bounded host adapter'
    return value


def binding():
    value = getattr(managed_tasks, 'registered_transfer_binding', None)
    assert callable(value), 'registered_transfer_binding must pin current persisted endpoint and credential'
    return value('source')


@pytest.mark.parametrize('named', [False, True])
def test_real_registered_peer_uses_source_credentials_and_never_forwards_local_context(tmp_path, monkeypatch, named):
    with registered_source(tmp_path, monkeypatch, named=named) as values:
        _server, exported, _body, _token, _book, _users = values
        monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
        witness = origin_policy.OriginWitness((tmp_path,))
        with origin_policy.origin_scope(witness.identifier):
            manifest = adapter()('source', binding(), '/agent/transfer/peer',
                                 {'operation': 'export', 'request': {'export_id': exported['export_id']}}, 3)
        assert manifest == exported['manifest']


@pytest.mark.parametrize('change', ['token', 'endpoint', 'removed'])
def test_another_real_clients_persisted_replacement_refuses_the_old_binding_before_wire(
        tmp_path, monkeypatch, change):
    with registered_source(tmp_path, monkeypatch) as values:
        server, exported, _body, token, book, _users = values
        pinned = binding()
        other = admin_client.AdminConsoleClient(persist_path=book.persist_path)
        if change == 'removed':
            assert other.remove_host('source')
        else:
            other.add_host('source', server.base_url + '/changed' if change == 'endpoint' else server.base_url,
                           'replacement-credential' if change == 'token' else token)
        assert book.list_hosts()[0].token == token and book.list_hosts()[0].base_url == server.base_url
        def forbidden(*_args, **_kwargs):
            raise AssertionError('replaced registration must fail before network dispatch')
        monkeypatch.setattr(transport, 'request_json', forbidden)
        with pytest.raises(AgentTaskError):
            adapter()('source', pinned, '/agent/transfer/peer',
                      {'operation': 'export', 'request': {'export_id': exported['export_id']}}, 3)


@pytest.mark.parametrize('change', ['registration', 'caller'])
def test_real_successful_reply_is_discarded_after_local_authority_changes(tmp_path, monkeypatch, change):
    with registered_source(tmp_path, monkeypatch) as values:
        server, exported, _body, _token, book, users = values
        pinned = binding()
        original = transport.request_json
        other = admin_client.AdminConsoleClient(persist_path=book.persist_path)
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            if change == 'registration':
                other.add_host('source', server.base_url, 'replaced-after-real-response')
            else:
                users.remove_user('coordinator')
            return result
        monkeypatch.setattr(transport, 'request_json', changed)
        with pytest.raises((AgentTaskError, AuthorizationError)):
            adapter()('source', pinned, '/agent/transfer/peer',
                      {'operation': 'export', 'request': {'export_id': exported['export_id']}}, 3)


@pytest.mark.parametrize('payload', [b'not json', b'[]', b'{"hosts":null}', b'{"hosts":[]}'])
def test_malformed_or_missing_current_registration_is_not_loaded_quarantined_or_dispatched(
        tmp_path, monkeypatch, payload):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, exported, _body, _token, book, _users = values
        pinned = binding()
        book.persist_path.write_bytes(payload)
        def forbidden(*_args, **_kwargs):
            raise AssertionError('invalid book must not load/quarantine or dispatch')
        monkeypatch.setattr(admin_client.AdminConsoleClient, '_load', forbidden)
        monkeypatch.setattr(transport, 'request_json', forbidden)
        with pytest.raises(AgentTaskError):
            adapter()('source', pinned, '/agent/transfer/peer',
                      {'operation': 'export', 'request': {'export_id': exported['export_id']}}, 3)
        assert book.persist_path.read_bytes() == payload


@pytest.mark.parametrize('path', ['/agent/submit', 'https://foreign.invalid/agent/transfer', '/agent/transfer?x=1'])
def test_transfer_adapter_refuses_other_routes_before_dispatch(tmp_path, monkeypatch, path):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, exported, _body, _token, _book, _users = values
        pinned = binding()
        def forbidden(*_args, **_kwargs):
            raise AssertionError('unapproved transfer route was dispatched')
        monkeypatch.setattr(transport, 'request_json', forbidden)
        with pytest.raises(AgentTaskError):
            adapter()('source', pinned, path,
                      {'operation': 'export', 'request': {'export_id': exported['export_id']}}, 3)


@pytest.mark.parametrize('change', ['empty_query', 'empty_fragment', 'credential_control'])
def test_unusable_registered_url_or_header_credential_is_not_pinned(tmp_path, monkeypatch, change):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, _exported, _body, _token, book, _users = values
        payload = json.loads(book.persist_path.read_text(encoding='utf-8'))
        entry = payload['hosts'][0]
        if change == 'credential_control':
            entry['token'] = 'owned-fixture\r\nX-Unreviewed: value'
        else:
            entry['base_url'] += '?' if change == 'empty_query' else '#'
        book.persist_path.write_text(json.dumps(payload), encoding='utf-8')
        with pytest.raises(AgentTaskError):
            binding()


@pytest.mark.parametrize('change', ['token', 'endpoint', 'removed'])
def test_a_separate_real_process_cannot_leave_a_cached_transfer_binding_authoritative(tmp_path, monkeypatch, change):
    with registered_source(tmp_path, monkeypatch) as values:
        server, exported, _body, token, book, _users = values
        pinned = binding()
        program = '''import json, sys
from pathlib import Path
from je_auto_control.utils.admin.admin_client import AdminConsoleClient
value = json.load(sys.stdin)
client = AdminConsoleClient(persist_path=Path(value['path']))
if value['change'] == 'removed':
    assert client.remove_host('source')
else:
    client.add_host('source', value['url'], value['token'])
'''
        payload = {'path': str(book.persist_path), 'change': change,
                   'url': server.base_url + '/changed' if change == 'endpoint' else server.base_url,
                   'token': 'separate-process-credential' if change == 'token' else token}
        result = subprocess.run([sys.executable, '-c', program], input=json.dumps(payload), text=True,
                                capture_output=True, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        assert result.returncode == 0, result.stderr
        def forbidden(*_args, **_kwargs):
            raise AssertionError('the stale registration was dispatched after a real process changed its book')
        monkeypatch.setattr(transport, 'request_json', forbidden)
        with pytest.raises(AgentTaskError):
            adapter()('source', pinned, '/agent/transfer/peer',
                      {'operation': 'export', 'request': {'export_id': exported['export_id']}}, 3)
        assert book.list_hosts()[0].token == token
        assert book.list_hosts()[0].base_url == server.base_url


def test_huge_transfer_timeout_is_a_typed_pre_dispatch_failure(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('huge transfer timeout reached a network request')
    monkeypatch.setattr(transport, 'request_json', forbidden)
    with pytest.raises(AgentTaskError):
        adapter()('source', 'f' * 64, '/agent/transfer/peer',
                  {'operation': 'export', 'request': {'export_id': 'a' * 32}}, 1 << 4096)
