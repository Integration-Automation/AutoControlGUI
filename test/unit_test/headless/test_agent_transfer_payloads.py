"""Real manifest tasks transfer empty files and multiple chunks, refusing partial or corrupt replies."""
import base64
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from threading import Event
import json
import time
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_import import import_hosts
from headless.test_agent_transfer_import_lifecycle import operation, review, wait_import
from headless.test_agent_transfer_peer_security import post
from headless._transfer_process import owned_transfer_process
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.agent_runtime.dag_batches import DagBatches
from je_auto_control.utils.agent_runtime.file_target import FileTarget
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.agent_runtime.transfer_cache import PrivateTransferCache
from je_auto_control.utils.config_sync.blob_models import CHUNK_BYTES
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.users import UserStore

FILES = {'empty.bin': b'', 'large.bin': b'a' * CHUNK_BYTES + b'b' * CHUNK_BYTES + b'c' * 41,
         'note.txt': 'independent 多檔案成果'.encode('utf-8')}


@contextmanager
def manifest_source(root, *, named):
    assert named
    for name, body in FILES.items():
        (root / name).write_bytes(body)
    users = UserStore(root / 'users.json')
    users.add_user(user_id='owner', display_name='Owner', role='operator')
    actor = AuthorizationContext('owner', 'operator', store_path=str(users.path))
    manifest = root / 'verified-file-manifest.json'
    runtime = AgentRuntime(root / 'runtime.sqlite3', targets={'local-files': FileTarget()})
    try:
        with authorization_scope(actor):
            task = runtime.submit({'goal': 'produce and independently verify the actual source manifest',
                'target': 'local-files', 'mode': 'skill', 'roots': [str(root)],
                'allowed_tools': ['AC_workflow_manifest'], 'actions': [{'tool': 'AC_workflow_manifest',
                    'arguments': {'directory': str(root), 'path': str(manifest), 'names': list(FILES)}}],
                'success_criteria': [{'kind': 'file_manifest', 'path': str(manifest),
                    'directory': str(root), 'names': list(FILES)}, {'kind': 'actions_complete'}]})
            assert run_task(runtime, task.task_id).state == 'succeeded'
        yield runtime, task.task_id, manifest, FILES, users
    finally:
        runtime.close()


@pytest.mark.parametrize('fault', ['none', 'empty-only', 'corrupt-second', 'drop-third', 'chunk-order'])
def test_real_http_multi_file_chunks_publish_only_a_complete_verified_generation(tmp_path, monkeypatch, fault):
    requests = []
    original = DagBatches.transfer_call
    def transport(batches, host, binding, path, body, timeout):
        reply = original(batches, host, binding, path, body, timeout)
        if path == '/agent/transfer/peer' and body['operation'] == 'export' and fault == 'chunk-order':
            reply = {**reply, 'files': [
                {**item, 'chunks': [item['chunks'][1], item['chunks'][0], *item['chunks'][2:]]}
                if item['name'] == 'large.bin' else item for item in reply['files']]}
        if path == '/agent/transfer/peer' and body['operation'] == 'chunk':
            requests.append(body['request']['sha256'])
            if fault == 'corrupt-second' and len(requests) == 2:
                data = base64.b64decode(reply['data'])
                reply = {**reply, 'data': base64.b64encode(bytes([data[0] ^ 255]) + data[1:]).decode('ascii')}
            if fault == 'drop-third' and len(requests) == 3:
                raise OSError('owned transport loss after actual source HTTP chunk reply')
        return reply
    monkeypatch.setattr(DagBatches, 'transfer_call', transport)
    selection = [{'criterion': 0, 'names': ['empty.bin'] if fault == 'empty-only' else list(FILES)}]
    with import_hosts(tmp_path, monkeypatch, source_context=manifest_source, selection=selection) as values:
        host, server, exported, bodies, token, root, _actor = values
        manifests = {item['name']: item for item in exported['manifest']['files']}
        assert manifests['empty.bin']['size'] == 0 and manifests['empty.bin']['chunks'] == []
        if 'large.bin' in manifests:
            assert len(manifests['large.bin']['chunks']) == 3
        status, reply = operation(server, token, 'create_import', review(server, exported, token, root))
        assert status == 200, reply
        identifier = reply['import']['import_id']
        current = wait_import(server, token, identifier)
        with host.runtime.store.connection() as connection:
            record = host.runtime.transfers.source.records.find(connection, identifier)
        cache = PrivateTransferCache(host.runtime.store.path)
        if fault in {'none', 'empty-only'}:
            assert current['state'] == 'published', current
            files = Path(current['files_directory'])
            assert {path.name for path in files.iterdir()} == set(manifests)
            for name in manifests:
                body = bodies[name]
                assert (files / name).read_bytes() == body
                assert sha256((files / name).read_bytes()).hexdigest() == manifests[name]['sha256']
            assert len(requests) == (0 if fault == 'empty-only' else 4)
        else:
            assert current['state'] == 'requires_review', current
            assert current['files_directory'] is None
            assert not (root / 'received').exists()
            assert record['held'] is True
            assert len(requests) == (2 if fault == 'corrupt-second' else 3)
            expected_chunks = 3 if fault == 'chunk-order' else len(requests) - 1
            assert cache.store.status(record['account'])['chunks'] == expected_chunks
            assert cache.store.status(record['account'])['blobs'] == 1, 'only the verified empty file may be committed'
            if fault == 'chunk-order':
                chunks = manifests['large.bin']['chunks']
                assert requests == [chunks[1], chunks[0], chunks[2]], 'all valid chunks reached full-blob verification'
        assert host.runtime.list() == []


@pytest.mark.parametrize('boundary', ['before-chunks', 'after-cache'])
def test_independent_source_expiry_refuses_surviving_chunks_without_expiring_the_destination(
        tmp_path, monkeypatch, boundary):
    source_directory = tmp_path / 'independent-source'
    with owned_transfer_process(source_directory, 'headless._transfer_source_process', {}) as source:
        with import_hosts(tmp_path, monkeypatch) as (host, server, _unused, _body, token, root, _actor):
            book = admin_client.AdminConsoleClient(persist_path=root / 'independent-source-hosts.json')
            book.add_host('source', source['url'], source['token'])
            monkeypatch.setattr(admin_client, '_default_console', book)
            entered, release = Event(), Event()
            from je_auto_control.utils.agent_runtime import transfer_import_files
            original = transfer_import_files.receive_chunks
            def paused(*args):
                if boundary == 'after-cache':
                    original(*args)
                entered.set()
                assert release.wait(10)
                if boundary == 'before-chunks':
                    return original(*args)
                return None
            monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', paused)
            try:
                status, reply = operation(server, token, 'create_import',
                    review(server, source['exported'], token, root))
                assert status == 200, reply
                identifier = reply['import']['import_id']
                assert entered.wait(5)
                with host.runtime.store.connection() as connection:
                    before = host.runtime.transfers.source.records.find(connection, identifier)
                if boundary == 'after-cache':
                    assert PrivateTransferCache(host.runtime.store.path).store.status(before['account'])['blobs'] == 3
                (source_directory / 'expire').touch()
                deadline = time.monotonic() + 5
                while not (source_directory / 'expired.json').exists():
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                expired = json.loads((source_directory / 'expired.json').read_text(encoding='utf-8'))
                assert expired['now'] > expired['expires'] == source['exported']['manifest']['expires']
                assert expired['private_chunks'] > 0
                source_server = SimpleNamespace(base_url=source['url'], token=source['token'])
                large = next(item for item in source['exported']['manifest']['files'] if item['name'] == 'large.bin')
                status, denied = post(source_server, '/agent/transfer/peer', {'operation': 'chunk', 'request': {
                    'export_id': source['exported']['export_id'],
                    'sha256': large['chunks'][0]}}, token=source['token'])
                assert status == 409, denied
                release.set()
                current = wait_import(server, token, identifier)
                assert current['state'] == 'requires_review', current
                assert current['files_directory'] is None
                with host.runtime.store.connection() as connection:
                    after = host.runtime.transfers.source.records.find(connection, identifier)
                assert after['expires'] == before['expires'] > time.time()
                assert after['scope'] == before['scope']
                assert after['held'] is True
                assert not (root / 'received').exists()
            finally:
                release.set()
