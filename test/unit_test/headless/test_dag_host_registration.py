"""Existing DAG transports revalidate actual persisted registrations and captured local authority."""
import json
import subprocess
import sys

import pytest

from headless.test_agent_transfer_registered import registered_source
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentTaskError, transport
from je_auto_control.utils.dag import managed_tasks
from je_auto_control.utils.rbac.authorization import AuthorizationError


def replace_from_process(book, change):
    """Change the real protected book from another interpreter without updating the old client cache."""
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
    host = book.list_hosts()[0]
    payload = {'path': str(book.persist_path), 'change': change,
               'url': host.base_url + '/replacement' if change == 'endpoint' else host.base_url,
               'token': 'replacement-owned-fixture-token' if change == 'token' else host.token}
    result = subprocess.run([sys.executable, '-c', program], input=json.dumps(payload), text=True,
                            capture_output=True, timeout=15,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('change', ['token', 'endpoint', 'removed'])
@pytest.mark.parametrize('boundary', ['binding', 'connection', 'retained'])
def test_another_process_invalidates_existing_dag_host_authority(tmp_path, monkeypatch, change, boundary):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, exported, _body, token, book, _users = values
        pinned = managed_tasks.task_host_binding('source')
        connection = managed_tasks.bound_task_connection('source', pinned)
        old_url = book.list_hosts()[0].base_url
        replace_from_process(book, change)
        assert book.list_hosts()[0].token == token and book.list_hosts()[0].base_url == old_url

        def forbidden(*_args, **_kwargs):
            raise AssertionError('stale DAG registration reached network dispatch')

        monkeypatch.setattr(transport, 'request_json', forbidden)
        if boundary == 'binding' and change != 'removed':
            assert managed_tasks.task_host_binding('source') != pinned
            return
        with pytest.raises(AgentTaskError):
            if boundary == 'binding':
                managed_tasks.task_host_binding('source')
            elif boundary == 'connection':
                managed_tasks.bound_task_connection('source', pinned)
            else:
                connection('get', {'task_id': exported['manifest']['source_task']}, 3)


@pytest.mark.parametrize('change', ['registration', 'caller'])
def test_existing_dag_connection_rejects_a_real_reply_after_authority_changes(tmp_path, monkeypatch, change):
    with registered_source(tmp_path, monkeypatch) as values:
        server, exported, _body, _token, book, users = values
        connection = managed_tasks.bound_task_connection('source', managed_tasks.task_host_binding('source'))
        original = transport.request_json
        other = admin_client.AdminConsoleClient(persist_path=book.persist_path)
        calls = []

        def changed(*args, **kwargs):
            reply = original(*args, **kwargs)
            calls.append(reply)
            if change == 'registration':
                other.add_host('source', server.base_url, 'replaced-after-actual-reply')
            else:
                users.remove_user('coordinator')
            return reply

        monkeypatch.setattr(transport, 'request_json', changed)
        with pytest.raises((AgentTaskError, AuthorizationError)):
            connection('get', {'task_id': exported['manifest']['source_task']}, 3)
        assert len(calls) == 1 and calls[0]['state'] == 'succeeded'


def test_unbound_dag_connection_also_rejects_a_later_registration_change(tmp_path, monkeypatch):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, exported, _body, _token, book, _users = values
        connection = managed_tasks.task_connection('source')
        replace_from_process(book, 'token')

        def forbidden(*_args, **_kwargs):
            raise AssertionError('unbound DAG connection retained a replaced credential')

        monkeypatch.setattr(transport, 'request_json', forbidden)
        with pytest.raises(AgentTaskError):
            connection('get', {'task_id': exported['manifest']['source_task']}, 3)


@pytest.mark.parametrize('payload', [b'not json', b'{"hosts":[]}', b'{"hosts":null}'])
def test_dag_binding_reads_invalid_current_configuration_without_loader_side_effects(tmp_path, monkeypatch, payload):
    with registered_source(tmp_path, monkeypatch) as values:
        _server, _exported, _body, _token, book, _users = values
        book.persist_path.write_bytes(payload)

        def forbidden(*_args, **_kwargs):
            raise AssertionError('DAG binding must neither initialize nor quarantine the host book')

        monkeypatch.setattr(admin_client.AdminConsoleClient, '_load', forbidden)
        with pytest.raises(AgentTaskError):
            managed_tasks.task_host_binding('source')
        assert book.persist_path.read_bytes() == payload
