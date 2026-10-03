"""Persistent CAS config writes cannot overwrite concurrent or retried edits."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncError


def store(path):
    from je_auto_control.utils.config_sync.store import ConfigStore
    return ConfigStore(path)


def bucket(user='alice', combo='ctrl+a'):
    return ConfigBucket(user, {'hotkeys': {'one': {'combo': combo, 'last_modified': 1}}})


def test_reopen_preserves_bucket(tmp_path):
    path = tmp_path / 'server.sqlite'
    original = store(path)
    committed_revision = original.commit('alice', bucket(), base_revision=0, operation_id='first')
    original.close()
    reopened = store(path)
    assert reopened.get('alice').revision == committed_revision
    assert reopened.get('alice').sections['hotkeys']['one']['combo'] == 'ctrl+a'
    reopened.close()


def test_operation_retry_is_idempotent(tmp_path):
    path = tmp_path / 'server.sqlite'
    original = store(path)
    revision = original.commit('alice', bucket(), base_revision=0, operation_id='first')
    original.close()
    repeated_store = store(path)
    repeated_revision = repeated_store.commit('alice', bucket(), base_revision=0, operation_id='first')
    original_bucket = ConfigBucket('alice', revision=revision)
    repeated = ConfigBucket('alice', revision=repeated_revision)
    assert repeated.revision == original_bucket.revision == 1
    repeated_store.close()


def test_competing_transactions_have_one_winner(tmp_path):
    path = tmp_path / 'server.sqlite'
    stores = [store(path), store(path)]

    def commit(index):
        try:
            return stores[index].commit('alice', bucket(combo=str(index)),
                                        base_revision=0, operation_id=f'writer-{index}')
        except ConfigSyncError:
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, [0, 1]))
    assert sorted(map(str, results)) == ['1', 'conflict']
    assert stores[0].get('alice').revision == 1
    for instance in stores:
        instance.close()


def test_reusing_operation_id_for_another_write_is_rejected(tmp_path):
    instance = store(tmp_path / 'server.sqlite')
    instance.commit('alice', bucket(), base_revision=0, operation_id='first')
    with pytest.raises(ConfigSyncError):
        instance.commit('alice', bucket(combo='ctrl+b'), base_revision=1, operation_id='first')
    assert instance.get('alice').sections['hotkeys']['one']['combo'] == 'ctrl+a'
    instance.close()


def test_store_namespaces_operations_and_buckets(tmp_path):
    instance = store(tmp_path / 'server.sqlite')
    instance.commit('alice', bucket(), base_revision=0, operation_id='same')
    instance.commit('bob', bucket('bob', 'ctrl+b'), base_revision=0, operation_id='same')
    assert instance.get('alice').sections['hotkeys']['one']['combo'] == 'ctrl+a'
    assert instance.get('bob').sections['hotkeys']['one']['combo'] == 'ctrl+b'
    with pytest.raises(ConfigSyncError):
        instance.commit('alice', bucket('bob'), base_revision=1, operation_id='wrong-account')
    instance.close()


def test_lazy_path_is_resolved_on_first_use(tmp_path):
    calls = []

    def resolve():
        calls.append(True)
        return tmp_path / 'lazy.sqlite'

    instance = store(resolve)
    assert calls == [] and not (tmp_path / 'lazy.sqlite').exists()
    instance.commit('alice', bucket(), base_revision=0, operation_id='first')
    assert calls == [True] and (tmp_path / 'lazy.sqlite').exists()
    instance.close()


def client(tmp_path, **options):
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    return TestClient(create_app(shared_secret='test-secret', serve_web_viewer=False,
                                 config_store_path=tmp_path / 'server.sqlite', **options))


SECRET = {'X-Signaling-Secret': 'test-secret'}


def envelope(*, base=0, operation='first', combo='ctrl+a'):
    return {'schema_version': 2, 'base_revision': base, 'operation_id': operation,
            'bucket': bucket(combo=combo).to_dict()}


def test_stale_revision_conflicts(tmp_path):
    with client(tmp_path) as http:
        assert http.put('/config/alice', json=envelope(), headers=SECRET).status_code == 200
        stale_response = http.put('/config/alice', json=envelope(operation='second', combo='ctrl+b'),
                                  headers=SECRET)
        assert stale_response.status_code == 409
        assert http.get('/config/alice', headers=SECRET).json()['revision'] == 1


def test_server_reopen_preserves_committed_revision(tmp_path):
    with client(tmp_path) as http:
        assert http.put('/config/alice', json=envelope(), headers=SECRET).json()['revision'] == 1
    with client(tmp_path) as reopened:
        response = reopened.get('/config/alice', headers=SECRET).json()
        assert response['revision'] == 1 and response['cas_supported'] is True
        assert reopened.put('/config/alice', json=envelope(), headers=SECRET).json()['revision'] == 1


def test_blind_write_requires_explicit_compatibility(tmp_path):
    with client(tmp_path) as http:
        assert http.put('/config/alice', json=bucket().to_dict(), headers=SECRET).status_code == 400
    with client(tmp_path, allow_legacy_config_writes=True) as legacy:
        assert legacy.put('/config/alice', json=bucket().to_dict(), headers=SECRET).status_code == 200
        assert legacy.get('/config/alice', headers=SECRET).json()['revision'] == 1


def test_protected_routes_preserve_auth_size_and_account_checks(tmp_path):
    with client(tmp_path) as http:
        assert http.put('/config/alice', json=envelope()).status_code == 401
        wrong = envelope()
        wrong['bucket']['user_id'] = 'bob'
        assert http.put('/config/alice', json=wrong, headers=SECRET).status_code == 400
        huge = b'"' + b'x' * (2 * 1024 * 1024) + b'"'
        assert http.put('/config/alice', content=huge, headers=SECRET).status_code == 413


@pytest.mark.parametrize('base', [True, -1, 1.5, '0'])
def test_invalid_base_revision_is_not_coerced(tmp_path, base):
    with client(tmp_path) as http:
        assert http.put('/config/alice', json=envelope(base=base), headers=SECRET).status_code == 400


@pytest.mark.parametrize('field,value', [('schema_version', True), ('schema_version', 3),
                                       ('operation_id', ''), ('operation_id', 15),
                                       ('bucket', {'user_id': 'alice', 'sections': {'x': []}})])
def test_invalid_envelope_does_not_create_state(tmp_path, field, value):
    with client(tmp_path) as http:
        invalid = envelope()
        invalid[field] = value
        assert http.put('/config/alice', json=invalid, headers=SECRET).status_code == 400
        assert http.get('/config/alice', headers=SECRET).status_code == 404


def test_browser_can_preflight_config_put(tmp_path):
    with client(tmp_path) as http:
        response = http.options('/config/alice', headers={
            'Origin': 'https://viewer.example', 'Access-Control-Request-Method': 'PUT',
            'Access-Control-Request-Headers': 'X-Signaling-Secret,Content-Type'})
        assert response.status_code == 200
        assert 'PUT' in response.headers['access-control-allow-methods']


def test_retry_after_another_write_returns_original_revision(tmp_path):
    instance = store(tmp_path / 'server.sqlite')
    instance.commit('alice', bucket(), base_revision=0, operation_id='first')
    instance.commit('alice', bucket(combo='ctrl+b'), base_revision=1, operation_id='second')
    assert instance.commit('alice', bucket(), base_revision=0, operation_id='first') == 1
    assert instance.get('alice').revision == 2
    assert instance.get('alice').sections['hotkeys']['one']['combo'] == 'ctrl+b'
    instance.close()


def test_user_cap_is_enforced_in_the_transaction(tmp_path):
    from je_auto_control.utils.config_sync.store import ConfigStore
    instance = ConfigStore(tmp_path / 'server.sqlite', max_users=1)
    instance.commit('alice', bucket(), base_revision=0, operation_id='first')
    with pytest.raises(ConfigSyncError):
        instance.commit('bob', bucket('bob'), base_revision=0, operation_id='second')
    assert instance.get('bob') is None
    instance.close()
