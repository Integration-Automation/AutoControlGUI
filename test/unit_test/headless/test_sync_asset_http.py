"""Bounded authenticated asset HTTP resumes immutable chunks and never reports incomplete or corrupt blobs as usable."""
from hashlib import sha256
import json
from urllib.parse import urlsplit

import pytest

import je_auto_control as ac

CHUNK = 256 * 1024


def descriptor(body):
    return ac.SyncAssetBlob(sha256(body).hexdigest(), len(body), tuple(
        sha256(body[index:index + CHUNK]).hexdigest() for index in range(0, len(body), CHUNK)))


@pytest.fixture
def transport(tmp_path, monkeypatch):
    pytest.importorskip('fastapi')
    pytest.importorskip('httpx')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    from je_auto_control.utils.http_client import http_client
    state = {'client': TestClient(create_app(serve_web_viewer=False, config_store_path=tmp_path / 'server.sqlite3',
                                             asset_store_path=tmp_path / 'server-assets.sqlite3')),
             'calls': [], 'after': None}
    def perform(call):
        state['calls'].append(call.copy())
        response = state['client'].request(call['method'], urlsplit(call['url']).path,
                                           content=call['body'], headers=call['headers'])
        if state['after']:
            state['after'](call, response)
        return {'status': response.status_code, 'text': response.text}
    monkeypatch.setattr(http_client, 'perform_call', perform)
    return state


def test_asset_http_upload_and_download_restart_with_exact_content(tmp_path, transport):
    sender = ac.SyncAssetStore(tmp_path / 'sender.sqlite3')
    body = b'first' * (CHUNK // 5 + 7) + b'last'
    blob = descriptor(body)
    for index, digest in enumerate(blob.chunks):
        sender.put_chunk('local-sender', digest, body[index * CHUNK:(index + 1) * CHUNK])
    sender.commit('local-sender', blob)
    client = ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='alice')
    assert client.upload(blob, sender, 'local-sender') is True
    assert client.upload(blob, sender, 'local-sender') is False
    receiver = ac.SyncAssetStore(tmp_path / 'receiver.sqlite3')
    assert client.download(blob, receiver, 'local-receiver') is True
    assert client.download(blob, receiver, 'local-receiver') is False
    with ac.SyncAssetStore(tmp_path / 'receiver.sqlite3').open('local-receiver', blob) as stream:
        assert stream.read() == body
    assert all(not call['follow_redirects'] for call in transport['calls'])
    other = ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='bob')
    with pytest.raises(ac.ConfigSyncError, match='unavailable'):
        other.download(blob, receiver, 'other')


def test_uncertain_chunk_reply_resumes_after_restart_without_reuploading_accepted_content(tmp_path, transport):
    sender = ac.SyncAssetStore(tmp_path / 'sender.sqlite3')
    body = b'a' * CHUNK + b'tail'
    blob = descriptor(body)
    for index, digest in enumerate(blob.chunks):
        sender.put_chunk('source', digest, body[index * CHUNK:(index + 1) * CHUNK])
    sender.commit('source', blob)
    lost = []
    def lose(call, _reply):
        if '/chunks/' in call['url'] and call['method'] == 'PUT' and not lost:
            lost.append(call['url'])
            raise OSError('controlled lost accepted chunk reply')
    transport['after'] = lose
    with pytest.raises(ac.ConfigSyncError):
        ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='alice').upload(blob, sender, 'source')
    transport['after'] = None
    transport['calls'].clear()
    assert ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='alice').upload(blob, sender, 'source')
    writes = [call['url'] for call in transport['calls'] if call['method'] == 'PUT' and '/chunks/' in call['url']]
    assert writes == ['https://controlled.invalid/config/alice/assets/chunks/' + blob.chunks[1]]


def test_asset_routes_refuse_unauthorized_and_oversized_bodies_before_storage(tmp_path):
    pytest.importorskip('fastapi')
    pytest.importorskip('httpx')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    path = tmp_path / 'assets.sqlite3'
    client = TestClient(create_app(shared_secret='controlled-secret', serve_web_viewer=False,
                                   config_store_path=tmp_path / 'config.sqlite3', asset_store_path=path))
    route = '/config/alice/assets/chunks/' + 'a' * 64
    assert client.put(route, content=b'{broken').status_code == 401
    assert client.put(route, content=b'x' * (1024 * 1024 + 1),
                      headers={'X-Signaling-Secret': 'controlled-secret'}).status_code == 413
    assert not path.exists()


def test_asset_http_live_credentials_and_prestart_cancellation(tmp_path, transport, monkeypatch):
    monkeypatch.setenv('SYNC_TEST_SECRET', 'before')
    body = b'bytes'
    blob = descriptor(body)
    sender = ac.SyncAssetStore(tmp_path / 'source.sqlite3')
    sender.put_chunk('source', blob.chunks[0], body)
    sender.commit('source', blob)
    def rotate(_call, _reply):
        monkeypatch.setenv('SYNC_TEST_SECRET', 'after')
    transport['after'] = rotate
    client = ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='alice', secret_env='SYNC_TEST_SECRET')
    client.upload(blob, sender, 'source')
    assert transport['calls'][0]['headers']['X-Signaling-Secret'] == 'before'
    assert all(call['headers']['X-Signaling-Secret'] == 'after' for call in transport['calls'][1:])
    from concurrent.futures import CancelledError
    cancelled = ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='alice', cancelled=lambda: True)
    target = ac.SyncAssetStore(tmp_path / 'never-created.sqlite3')
    with pytest.raises(CancelledError):
        cancelled.download(blob, target, 'target')
    assert not (tmp_path / 'never-created.sqlite3').exists()


def test_invalid_asset_reply_never_reaches_a_target_cache(tmp_path, transport, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    blob = descriptor(b'bytes')
    monkeypatch.setattr(http_client, 'perform_call', lambda _call: {
        'status': 200, 'text': json.dumps({'version': 1, 'complete': 'yes', 'missing': []})})
    target = ac.SyncAssetStore(tmp_path / 'target.sqlite3')
    with pytest.raises(ac.SyncWorkspaceError, match='asset'):
        ac.SyncAssetHTTPClient('https://controlled.invalid', user_id='alice').download(blob, target, 'target')
    assert not target.contains('target', blob)
