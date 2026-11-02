"""Three actual runtimes route source B to a separate-process destination C using only C's source registry."""
from contextlib import closing, contextmanager
from copy import deepcopy
import json
from pathlib import Path
import time
import sqlite3
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_peer_security import approved_export, source_server
from headless._transfer_process import owned_transfer_process
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError, transport
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@contextmanager
def destination_process(directory, source, token):
    with owned_transfer_process(directory, 'headless._transfer_destination_process',
                                {'source_url': source.base_url, 'source_token': token}) as metadata:
        yield metadata


@contextmanager
def three_hosts(tmp_path, monkeypatch):
    source_root = tmp_path / 'source'
    source_root.mkdir()
    with source_server(source_root, named=True) as (source, task, body, source_users):
        source_token = source_users.rotate_token('owner')
        exported = approved_export(source, task, token=source_token)
        with destination_process(tmp_path / 'destination', source, source_token) as destination:
            users = UserStore(tmp_path / 'coordinator-users.json')
            users.add_user(user_id='coordinator', display_name='Coordinator', role='admin')
            actor = AuthorizationContext('coordinator', 'admin', store_path=str(users.path))
            book = admin_client.AdminConsoleClient(persist_path=tmp_path / 'coordinator-hosts.json')
            book.add_host('destination', destination['url'], destination['token'])
            book.add_host('source', source.base_url, 'deliberately-unusable-coordinator-source-token')
            monkeypatch.setattr(admin_client, '_default_console', book)
            runtime = AgentRuntime(tmp_path / 'coordinator.sqlite3', targets={})
            wire, original = [], transport.request_json
            def observe(url, **kwargs):
                envelope = kwargs.get('body')
                if url.startswith(destination['url']) and isinstance(envelope, dict):
                    assert kwargs.get('delegate_local') is False
                    assert kwargs['token'] == destination['token']
                    record = deepcopy(envelope)
                    wire.append(record)
                    reply = original(url, **kwargs)
                    record['reply'] = deepcopy(reply)
                    return reply
                return original(url, **kwargs)
            monkeypatch.setattr(transport, 'request_json', observe)
            value = SimpleNamespace(runtime=runtime, actor=actor, users=users, book=book, wire=wire,
                source=source, source_token=source_token, exported=exported, destination=destination, body=body)
            try:
                with authorization_scope(actor):
                    yield value
            finally:
                value.runtime.close()


def test_three_hosts_use_destination_credentials_and_publish_actual_source_bytes(tmp_path, monkeypatch):
    with three_hosts(tmp_path, monkeypatch) as hosts:
        directory = str(Path(hosts.destination['outputs']) / 'received')
        wrong = tmp_path / 'coordinator-local'
        wrong.mkdir()
        (wrong / 'report.txt').write_bytes(b'wrong coordinator bytes')
        reviewed = hosts.runtime.transfers.control('review_import', {'host': 'destination', 'source_host': 'source',
            'export_id': hosts.exported['export_id'], 'target': 'import-files', 'directory': directory,
            'idempotency_key': 'routed-import'})
        assert reviewed['review'] != hosts.wire[-1]['reply']['review'], 'coordinator consent must use a local token'
        assert reviewed['manifest'] == hosts.exported['manifest']
        created = hosts.runtime.transfers.control('create_import', {'host': 'destination', 'review': reviewed['review'],
            'note': 'Approve exact B source bytes at C', 'idempotency_key': 'routed-import'})['import']
        deadline = time.monotonic() + 20
        current = created
        while current['state'] not in {'published', 'requires_review', 'cancelled', 'expired'}:
            assert time.monotonic() < deadline, current
            time.sleep(0.25)
            current = hosts.runtime.transfers.control('get_import', {
                'host': 'destination', 'import_id': created['import_id']})['import']
        assert current['state'] == 'published', current
        assert (Path(current['files_directory']) / 'report.txt').read_bytes() == hosts.body
        assert (wrong / 'report.txt').read_bytes() == b'wrong coordinator bytes'
        assert hosts.runtime.list() == []
        public_wire = json.dumps(hosts.wire)
        assert hosts.source_token not in public_wire
        assert json.dumps(str(hosts.users.path))[1:-1] not in public_wire
        assert hosts.actor.user_id not in public_wire
        destination_root = Path(hosts.destination['outputs']).parent
        database = destination_root / 'service' / 'agent_runtime.sqlite'
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
            payload = connection.execute('SELECT payload FROM agent_transfer_imports WHERE id=?',
                                         (created['import_id'],)).fetchone()[0]
        scope = json.loads(payload)['scope']
        assert scope['issuer']['user_id'] == 'recipient'
        assert scope['issuer']['store_path'] == str(destination_root / 'users.json')
        assert scope['binding'] != hosts.runtime.batches.transfer_binding('source')


def reviewed_import(hosts, key='routed-import'):
    return hosts.runtime.transfers.control('review_import', {'host': 'destination', 'source_host': 'source',
        'export_id': hosts.exported['export_id'], 'target': 'import-files',
        'directory': str(Path(hosts.destination['outputs']) / key), 'idempotency_key': key})


def create_import(hosts, reviewed, key='routed-import', **changes):
    return hosts.runtime.transfers.control('create_import', {'host': 'destination', 'review': reviewed['review'],
        'note': 'Approve exact B source bytes at C', 'idempotency_key': key, **changes})


def test_routed_import_refuses_raw_peer_review_and_cross_operation_replay_before_wire(tmp_path, monkeypatch):
    with three_hosts(tmp_path, monkeypatch) as hosts:
        reviewed = reviewed_import(hosts)
        raw_review = hosts.wire[-1]['reply']['review']
        count = len(hosts.wire)
        with pytest.raises(AgentTaskError):
            create_import(hosts, {'review': raw_review})
        with pytest.raises(AgentTaskError):
            hosts.runtime.transfers.control('create_export', {'host': 'destination', 'review': reviewed['review'],
                'note': 'Approve exact B source bytes at C', 'idempotency_key': 'routed-import'})
        hosts.users.add_user(user_id='other', display_name='Other coordinator', role='admin')
        other = AuthorizationContext('other', 'admin', store_path=str(hosts.users.path))
        with authorization_scope(other), pytest.raises(AgentTaskError):
            create_import(hosts, reviewed)
        assert len(hosts.wire) == count
        created = create_import(hosts, reviewed)['import']
        imports = hosts.runtime.transfers.control('list_imports', {'host': 'destination'})['imports']
        assert [item['import_id'] for item in imports] == [created['import_id']]


def test_routed_import_rejects_another_clients_persisted_destination_replacement(tmp_path, monkeypatch):
    with three_hosts(tmp_path, monkeypatch) as hosts:
        reviewed = reviewed_import(hosts)
        other = admin_client.AdminConsoleClient(persist_path=hosts.book.persist_path)
        other.add_host('destination', hosts.destination['url'], 'replaced-destination-credential')
        count = len(hosts.wire)
        with pytest.raises(AgentTaskError):
            create_import(hosts, reviewed)
        assert len(hosts.wire) == count, 'the original private peer review cannot authorize a replacement host'


def test_lost_destination_create_ack_and_coordinator_restart_keep_one_exact_import(tmp_path, monkeypatch):
    with three_hosts(tmp_path, monkeypatch) as hosts:
        reviewed = reviewed_import(hosts)
        actual_transport = transport.request_json
        lost = []
        def lose_reply(url, **kwargs):
            reply = actual_transport(url, **kwargs)
            if kwargs.get('body', {}).get('operation') == 'create_import' and not lost:
                lost.append(reply['import']['import_id'])
                raise OSError('owned lost acknowledgement after the actual destination accepted')
            return reply
        monkeypatch.setattr(transport, 'request_json', lose_reply)
        with pytest.raises(AgentTaskError):
            create_import(hosts, reviewed)
        assert len(lost) == 1
        monkeypatch.setattr(transport, 'request_json', actual_transport)
        path = hosts.runtime.store.path
        hosts.runtime.close()
        hosts.runtime = AgentRuntime(path, targets={})
        repeated = create_import(hosts, reviewed)['import']
        assert repeated['import_id'] == lost[0]
        imports = hosts.runtime.transfers.control('list_imports', {'host': 'destination'})['imports']
        assert [item['import_id'] for item in imports] == lost
        with pytest.raises(AgentTaskError):
            create_import(hosts, reviewed, note='Different approval after the lost reply')
