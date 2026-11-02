"""Real named source/destination HTTP runtimes publish independently verified files through owned service work."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import time

import pytest

from headless.test_agent_transfer_source import completed_source
from headless.test_agent_transfer_peer_security import approved_export, post
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore


@contextmanager
def import_hosts(tmp_path, monkeypatch, *, source_context=None, selection=None):
    source_root, destination_root = tmp_path / 'source', tmp_path / 'destination'
    source_root.mkdir()
    destination_root.mkdir()
    provider = completed_source if source_context is None else source_context
    with provider(source_root, named=True) as (runtime, task, _file, body, source_users):
        source = RestApiServer(port=0, token='owned-source-service', user_store=source_users,
                               agent_runtime=runtime, enable_audit=False, use_environment_users=False)
        destination = AgentRuntimeService(destination_root / 'service', targets={})
        users = UserStore(destination_root / 'users.json')
        users.add_user(user_id='recipient', display_name='Recipient', role='admin')
        users.add_user(user_id='other', display_name='Other', role='admin')
        actor = AuthorizationContext('recipient', 'admin', store_path=str(users.path))
        root = destination_root / 'outputs'
        root.mkdir()
        with authorization_scope(actor):
            destination.runtime.target_profiles.control('register', {'name': 'import-files', 'kind': 'files',
                'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(root)], 'apps': [], 'settings': {}})
        named = RestApiServer(port=0, token='owned-destination-service', user_store=users,
                              agent_runtime=destination.runtime, enable_audit=False, use_environment_users=False)
        try:
            source.start()
            destination.start()
            named.start()
            source_token = source_users.rotate_token('owner')
            exported = approved_export(source, task, token=source_token, selection=selection)
            book = admin_client.AdminConsoleClient(persist_path=destination_root / 'source-hosts.json')
            book.add_host('source', source.base_url, source_token)
            monkeypatch.setattr(admin_client, '_default_console', book)
            yield destination, named, exported, body, users.rotate_token('recipient'), root, actor
        finally:
            named.stop()
            destination.close()
            source.stop()


def test_actual_source_bytes_reach_only_the_approved_destination_generation(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, _actor):
        output = root / 'received'
        local_substitute = tmp_path / 'coordinator' / 'received'
        local_substitute.mkdir(parents=True)
        (local_substitute / 'report.txt').write_bytes(b'wrong coordinator-local bytes')
        status, reviewed = post(server, '/agent/transfer', {'operation': 'review_import', 'request': {
            'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
            'directory': str(output), 'idempotency_key': 'reviewed-import'}}, token=token)
        assert status == 200, reviewed
        assert reviewed['approval_required'] is True
        assert not output.exists(), 'review must not create user output'
        status, created = post(server, '/agent/transfer', {'operation': 'create_import', 'request': {
            'review': reviewed['review'], 'note': 'Approve only this source manifest and destination',
            'idempotency_key': 'reviewed-import'}}, token=token)
        assert status == 200, created
        identifier = created['import']['import_id']
        deadline = time.monotonic() + 20
        current = created['import']
        while current['state'] not in {'published', 'requires_review', 'cancelled', 'expired'}:
            assert time.monotonic() < deadline, current
            status, reply = post(server, '/agent/transfer', {'operation': 'get_import',
                'request': {'import_id': identifier}}, token=token)
            assert status == 200, reply
            current = reply['import']
            if current['state'] != 'published':
                time.sleep(0.05)
        assert current['state'] == 'published', current
        files = Path(current['files_directory'])
        assert files.resolve().is_relative_to(output.resolve())
        assert (files / 'report.txt').read_bytes() == body
        assert sha256((files / 'report.txt').read_bytes()).hexdigest() == exported['manifest']['files'][0]['sha256']
        assert {path.name for path in files.iterdir()} == {'report.txt'}
        assert (local_substitute / 'report.txt').read_bytes() == b'wrong coordinator-local bytes'
        assert host.runtime.list() == [], 'an import is not an ordinary task or a synthetic completion proof'


def test_import_review_fetches_the_actual_source_manifest_without_writing_output(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        output = root / 'review-only'
        status, reviewed = post(server, '/agent/transfer', {'operation': 'review_import', 'request': {
            'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
            'directory': str(output), 'idempotency_key': 'review-only'}}, token=token)
        assert status == 200, reviewed
        assert reviewed['manifest'] == exported['manifest']
        assert reviewed['approval_required'] is True
        assert not output.exists()
        assert host.runtime.list() == []


@pytest.mark.parametrize('change', ['outside', 'missing-target', 'unknown-field', 'blank-key', 'local-source'])
def test_invalid_import_review_never_creates_output(tmp_path, monkeypatch, change):
    with import_hosts(tmp_path, monkeypatch) as (_host, server, exported, _body, token, root, _actor):
        output = root / 'refused'
        request = {'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
                   'directory': str(output), 'idempotency_key': 'refused'}
        request.update({'outside': {'directory': str(root.parent)}, 'missing-target': {'target': 'local-files'},
                        'unknown-field': {'account': 'a' * 32}, 'blank-key': {'idempotency_key': ''},
                        'local-source': {'source_host': 'local'}}[change])
        status, _reply = post(server, '/agent/transfer',
                              {'operation': 'review_import', 'request': request}, token=token)
        assert status == 409
        assert not output.exists()


def test_create_import_requires_the_reviewed_key_and_actual_recipient(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (_host, server, exported, _body, token, root, actor):
        status, reviewed = post(server, '/agent/transfer', {'operation': 'review_import', 'request': {
            'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
            'directory': str(root / 'approved'), 'idempotency_key': 'same-key'}}, token=token)
        assert status == 200, reviewed
        request = {'review': reviewed['review'], 'note': 'Approved import', 'idempotency_key': 'same-key'}
        other = UserStore(actor.store_path).rotate_token('other')
        for credential, values in ((other, request), (token, {**request, 'idempotency_key': 'different-key'})):
            status, _reply = post(server, '/agent/transfer', {'operation': 'create_import', 'request': values},
                                  token=credential)
            assert status == 409
        status, created = post(server, '/agent/transfer',
                               {'operation': 'create_import', 'request': request}, token=token)
        assert status == 200, created
        status, repeated = post(server, '/agent/transfer',
                                {'operation': 'create_import', 'request': request}, token=token)
        assert status == 200, repeated
        assert repeated['import']['import_id'] == created['import']['import_id']
        status, _reply = post(server, '/agent/transfer', {'operation': 'create_import',
            'request': {**request, 'note': 'Different approval'}}, token=token)
        assert status == 409


def test_malformed_review_fields_fail_before_any_peer_or_file_effect(tmp_path, monkeypatch):
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, _body, token, root, _actor):
        request = {'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
                   'directory': str(root / 'refused'), 'idempotency_key': 'refused'}
        for field, invalid in [('source_host', []), ('source_host', {}), ('source_host', True),
                               ('target', []), ('directory', None), ('export_id', []), ('idempotency_key', [])]:
            status, reply = post(server, '/agent/transfer', {'operation': 'review_import',
                'request': {**request, field: invalid}}, token=token)
            assert status == 409, (field, invalid, status, reply)
        assert not (root / 'refused').exists()
        assert host.runtime.list() == []
