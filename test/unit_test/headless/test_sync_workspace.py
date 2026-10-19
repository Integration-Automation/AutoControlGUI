"""Coordinate native profiles, causal HTTP and durable generations without activating received definitions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import je_auto_control as ac
from headless.causal_transport import perform_causal_call

ENDPOINT = 'https://controlled.invalid'
OPTIONS = {'policy': {'max_attempts': 1, 'backoff': 0}}


@pytest.fixture
def transport(tmp_path, monkeypatch):
    from je_auto_control.utils.http_client import http_client
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    state = {'server': ac.CausalConfigStore(tmp_path / 'server.sqlite3'), 'calls': [], 'after': None}
    def request(call):
        state['calls'].append(deepcopy(call))
        result = perform_causal_call(state['server'], call)
        if state['after'] is not None:
            state['after'](call, result)
        return result
    monkeypatch.setattr(http_client, 'perform_call', request)
    return state


def build_workspace(tmp_path, origin, *, theme=None):
    root = tmp_path / origin
    root.mkdir()
    source = root / 'gui.ini'
    if theme is not None:
        source.write_text('[workspace]\ntheme=' + theme + '\n', encoding='utf-8')
    path = root / 'outbox.sqlite3'
    ac.SyncOutbox(path).identity(ENDPOINT, 'alice', origin=origin)
    config = {'schema_version': 1, 'endpoint': ENDPOINT, 'user_id': 'alice', 'outbox_path': str(path),
              'profiles': [{'kind': 'workspace', 'state_path': str(root / 'adapters.sqlite3'),
                            'source': {'path': str(source)}}]}
    return ac.SyncWorkspace(config), config


def test_workspace_capture_is_offline_restart_stable_and_sync_materializes_an_inert_profile(tmp_path, transport):
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    assert workspace.capture() == 1
    assert not transport['calls']
    assert ac.SyncWorkspace(config).capture() == 0
    result = workspace.synchronize(options=OPTIONS)
    assert result.delivered == 1 and result.pending == 0 and not result.conflicts
    remote, remote_config = build_workspace(tmp_path, 'laptop')
    remote.synchronize(options=OPTIONS)
    generation = remote.materialize(tmp_path / 'cache')
    assert 'theme=light' in (generation.directory / 'workspace.ini').read_text(encoding='utf-8')
    assert not Path(remote_config['profiles'][0]['source']['path']).exists()
    assert workspace.status()['revision'] > 0


def test_two_workspace_sources_keep_concurrent_values_until_exact_reviewed_resolution(tmp_path, transport):
    left, _ = build_workspace(tmp_path, 'desktop', theme='light')
    right, _ = build_workspace(tmp_path, 'laptop', theme='dark')
    left.capture()
    right.capture()
    left.synchronize(options=OPTIONS)
    assert right.synchronize(options=OPTIONS).conflicts == (('workspace', 'theme'),)
    assert left.synchronize(options=OPTIONS).conflicts == (('workspace', 'theme'),)
    with pytest.raises(ac.ConfigSyncError):
        left.materialize(tmp_path / 'cache')
    heads = left.review('workspace')
    left.resolve('workspace', 'theme', {'value': 'light'}, observed=tuple(heads))
    left.synchronize(options=OPTIONS)
    assert not right.synchronize(options=OPTIONS).conflicts
    assert right.review('workspace') == left.review('workspace')
    assert (tmp_path / 'laptop/gui.ini').read_text(encoding='utf-8') == '[workspace]\ntheme=dark\n'


def test_uncertain_edit_retries_the_frozen_put_before_any_get_after_restart(tmp_path, transport):
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    lost = []
    def lose_receipt(call, _result):
        body = json.loads(call['body']) if call['method'] == 'PUT' else None
        if body and body['bucket']['_actor']['mode'] == 'edit' and not lost:
            lost.append(deepcopy(call))
            raise OSError('controlled accepted edit lost its reply')
    transport['after'] = lose_receipt
    report = workspace.synchronize(options=OPTIONS)
    assert report.pending == 1
    transport['after'] = None
    transport['calls'].clear()
    assert ac.SyncWorkspace(config).synchronize(options=OPTIONS).pending == 0
    assert transport['calls'][0]['method'] == 'PUT'
    assert transport['calls'][0]['body'] == lost[0]['body']


def test_invalid_remote_domain_data_is_not_prepared_or_cached_in_the_client(tmp_path, transport):
    seed = ac.SyncOutbox(tmp_path / 'seed.sqlite3')
    seed.identity(ENDPOINT, 'alice', origin='malicious-peer')
    generic = ac.CausalSyncClient(ENDPOINT, user_id='alice')
    generic.control(seed, 'register')
    raw = ac.SyncEntry('settings', 'password', {'value': 'remote-credential-never-cache'},
                       {'malicious-peer': 1}, 'raw-secret', 'malicious-peer')
    seed.enqueue(ac.SyncOperation('raw-delivery', ENDPOINT, 'alice', 'malicious-peer', (raw,)))
    assert generic.flush(seed).delivered == 1
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    with pytest.raises(ac.SyncWorkspaceError, match='snapshot'):
        workspace.synchronize(options=OPTIONS)
    queue = ac.SyncOutbox(config['outbox_path'])
    assert queue.snapshot(endpoint=ENDPOINT, user_id='alice') is None
    assert all(item.prepared is None for item in queue.pending(endpoint=ENDPOINT, user_id='alice'))
    for path in (tmp_path / 'desktop').glob('*.sqlite3'):
        assert b'remote-credential-never-cache' not in path.read_bytes()


def test_full_resync_adopts_source_baselines_without_replaying_retired_local_files(tmp_path, transport):
    left, _ = build_workspace(tmp_path, 'desktop', theme='light')
    right, config = build_workspace(tmp_path, 'laptop')
    left.synchronize(options=OPTIONS)
    right.synchronize(options=OPTIONS)
    source = tmp_path / 'laptop/gui.ini'
    source.write_text('[workspace]\ntheme=dark\n', encoding='utf-8')
    assert right.capture() == 1
    left.control(ac.SyncControlRequest('retire', peer_id='laptop'), options=OPTIONS)
    right.control(ac.SyncControlRequest('full_resync', operation_id='recover', discard_pending=True), options=OPTIONS)
    assert right.capture() == 0
    assert right.status()['outbox']['retired'] == 1
    assert next(iter(right.review('workspace').values())).value == {'value': 'light'}
    assert source.read_text(encoding='utf-8') == '[workspace]\ntheme=dark\n'
    assert ac.SyncOutbox(config['outbox_path']).identity(ENDPOINT, 'alice').epoch == 1
    source.write_text('[workspace]\ntheme=dark\nfont_pt=16\n', encoding='utf-8')
    assert right.capture() == 1
    right.synchronize(options=OPTIONS)
    assert any(entry.entry_id == 'font_pt' for entry in transport['server'].get('alice').entries)


def test_uncertain_resync_keeps_its_original_source_baseline_across_restart(tmp_path, transport):
    left, _ = build_workspace(tmp_path, 'desktop', theme='light')
    right, config = build_workspace(tmp_path, 'laptop')
    left.synchronize(options=OPTIONS)
    right.synchronize(options=OPTIONS)
    source = tmp_path / 'laptop/gui.ini'
    source.write_text('[workspace]\ntheme=dark\n', encoding='utf-8')
    right.capture()
    left.control(ac.SyncControlRequest('retire', peer_id='laptop'), options=OPTIONS)
    lost = []
    def lose_resync(call, _result):
        body = json.loads(call['body']) if call['method'] == 'PUT' else None
        if body and body['bucket']['_actor']['mode'] == 'full_sync' and not lost:
            lost.append(deepcopy(call))
            raise OSError('controlled accepted full resync lost its reply')
    transport['after'] = lose_resync
    result = right.control(ac.SyncControlRequest('full_resync', operation_id='recover', discard_pending=True),
                           options=OPTIONS)
    assert result.pending == 1
    source.write_text('[workspace]\ntheme=dark\nfont_pt=16\n', encoding='utf-8')
    transport['after'] = None
    transport['calls'].clear()
    result = ac.SyncWorkspace(config).synchronize(options=OPTIONS)
    assert result.pending == 0
    assert transport['calls'][0]['method'] == 'PUT' and transport['calls'][0]['body'] == lost[0]['body']
    current = transport['server'].get('alice')
    assert any(entry.entry_id == 'font_pt' for entry in current.entries)
    assert all(entry.value != {'value': 'dark'} for entry in current.entries)


def test_workspace_consumes_collected_deletion_fences_without_resurrecting_old_profiles(tmp_path, transport):
    left, _ = build_workspace(tmp_path, 'desktop', theme='light')
    right, config = build_workspace(tmp_path, 'laptop')
    left.synchronize(options=OPTIONS)
    right.synchronize(options=OPTIONS)
    (tmp_path / 'desktop/gui.ini').write_text('[workspace]\n', encoding='utf-8')
    left.synchronize(options=OPTIONS)
    generic = ac.CausalSyncClient(ENDPOINT, user_id='alice')
    generic.control(ac.SyncOutbox(config['outbox_path']), 'ack')
    left.control('ack', options=OPTIONS)
    left.control('collect', options=OPTIONS)
    assert transport['server'].get('alice').fences
    right.synchronize(options=OPTIONS)
    assert next(iter(right.review('workspace').values())).is_deleted
    result = right.materialize(tmp_path / 'cache')
    assert 'theme=dark' in (result.directory / 'workspace.ini').read_text(encoding='utf-8')


def test_workspace_status_is_local_and_does_not_read_a_configured_credential(tmp_path, transport, monkeypatch):
    workspace, _ = build_workspace(tmp_path, 'desktop', theme='light')
    monkeypatch.delenv('UNSET_SYNC_WORKSPACE_CREDENTIAL', raising=False)
    assert workspace.status()['outbox']['pending'] == 0
    assert not transport['calls']
    report = workspace.synchronize(options={**OPTIONS, 'secret_env': 'UNSET_SYNC_WORKSPACE_CREDENTIAL'})
    assert report.pending
    assert not transport['calls']


def test_workspace_refreshes_credentials_and_masks_late_transport_errors(tmp_path, transport, monkeypatch):
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    old, new = 'controlled-workspace-credential-before', 'controlled-workspace-credential-after'
    monkeypatch.setenv('WORKSPACE_CREDENTIAL', old)
    def rotate_and_fail(call, _result):
        if call['method'] == 'GET':
            monkeypatch.setenv('WORKSPACE_CREDENTIAL', new)
        elif json.loads(call['body'])['bucket']['_actor']['mode'] == 'edit':
            raise OSError('controlled late credential transport error ' + new)
    transport['after'] = rotate_and_fail
    result = workspace.synchronize(options={**OPTIONS, 'secret_env': 'WORKSPACE_CREDENTIAL'})
    assert result.pending == 1
    assert transport['calls'][0]['headers']['X-Signaling-Secret'] == old
    assert all(call['headers']['X-Signaling-Secret'] == new for call in transport['calls'][1:])
    for path in Path(config['outbox_path']).parent.glob('*.sqlite3'):
        assert old.encode() not in path.read_bytes() and new.encode() not in path.read_bytes()


def test_configured_network_credential_is_known_before_capturing_source_data(tmp_path, transport, monkeypatch):
    _workspace, config = build_workspace(tmp_path, 'desktop')
    source = tmp_path / 'desktop/settings.json'
    source.write_text('{"note":"short-lease-key"}', encoding='utf-8')
    config['profiles'] = [{'kind': 'settings', 'state_path': str(tmp_path / 'desktop/state.sqlite3'),
                           'source': {'path': str(source)}}]
    monkeypatch.setenv('WORKSPACE_CREDENTIAL', 'short-lease-key')
    with pytest.raises(ac.ConfigSyncError, match='credential'):
        ac.SyncWorkspace(config).synchronize(options={**OPTIONS, 'secret_env': 'WORKSPACE_CREDENTIAL'})
    assert not transport['calls']
    for path in (tmp_path / 'desktop').glob('*.sqlite3'):
        assert b'short-lease-key' not in path.read_bytes()


def test_credential_rotation_is_revalidated_before_preparing_or_sending_an_edit(tmp_path, transport, monkeypatch):
    workspace, config = build_workspace(tmp_path, 'desktop')
    monkeypatch.setenv('WORKSPACE_CREDENTIAL', 'old-credential')
    workspace.synchronize(options={**OPTIONS, 'secret_env': 'WORKSPACE_CREDENTIAL'})
    source = tmp_path / 'desktop/settings.json'
    source.write_text('{"note":"becomes-secret"}', encoding='utf-8')
    config['profiles'] = [{'kind': 'settings', 'state_path': str(tmp_path / 'desktop/state.sqlite3'),
                           'source': {'path': str(source)}}]
    def rotate(call, _result):
        if call['method'] == 'GET':
            monkeypatch.setenv('WORKSPACE_CREDENTIAL', 'becomes-secret')
    transport['after'] = rotate
    transport['calls'].clear()
    with pytest.raises(ac.SyncWorkspaceError, match='snapshot'):
        ac.SyncWorkspace(config).synchronize(options={**OPTIONS, 'secret_env': 'WORKSPACE_CREDENTIAL'})
    assert all(call['method'] == 'GET' for call in transport['calls'])
    queue = ac.SyncOutbox(config['outbox_path'])
    assert all(item.prepared is None for item in queue.pending(endpoint=ENDPOINT, user_id='alice'))


def test_cancellation_after_an_accepted_edit_keeps_its_confirmed_receipt(tmp_path, transport):
    from concurrent.futures import CancelledError
    from threading import Event
    _workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    stop = Event()
    workspace = ac.SyncWorkspace(config, cancelled=stop.is_set)
    def stop_after_edit(call, _result):
        if call['method'] == 'PUT' and json.loads(call['body'])['bucket']['_actor']['mode'] == 'edit':
            stop.set()
    transport['after'] = stop_after_edit
    with pytest.raises(CancelledError):
        workspace.synchronize(options=OPTIONS)
    queue = ac.SyncOutbox(config['outbox_path'])
    assert queue.status(endpoint=ENDPOINT, user_id='alice')['pending'] == 0
    assert queue.snapshot(endpoint=ENDPOINT, user_id='alice').entries
    transport['after'] = None
    assert ac.SyncWorkspace(config).synchronize(options=OPTIONS).pending == 0


def test_second_coordinator_cannot_capture_while_the_first_owns_the_namespace(tmp_path, transport):
    from threading import Event, Thread
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    entered, release = Event(), Event()
    results = []
    def block_first_get(call, _result):
        if call['method'] == 'GET' and not entered.is_set():
            entered.set()
            assert release.wait(5)
    transport['after'] = block_first_get
    def run():
        results.append(workspace.synchronize(options=OPTIONS))
    worker = Thread(target=run)
    worker.start()
    try:
        assert entered.wait(5)
        with pytest.raises(ac.SyncWorkspaceError, match='active'):
            ac.SyncWorkspace(config).capture()
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and results[0].pending == 0


def test_cancelled_constructor_and_invalid_configuration_open_no_databases(tmp_path, monkeypatch):
    from concurrent.futures import CancelledError
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    config = {'schema_version': 1, 'endpoint': ENDPOINT, 'user_id': 'alice',
              'outbox_path': str(tmp_path / 'outbox.sqlite3'), 'profiles': [
                  {'kind': 'workspace', 'state_path': str(tmp_path / 'state.sqlite3'),
                   'source': {'records': {}}}]}
    with pytest.raises(CancelledError):
        ac.SyncWorkspace(config, cancelled=lambda: True)
    wrong = deepcopy(config)
    wrong['profiles'][0]['kind'] = []
    with pytest.raises(ac.ConfigSyncError):
        ac.SyncWorkspace(wrong)
    assert not list(tmp_path.glob('*.sqlite3'))


@pytest.mark.parametrize('alias', ['state-outbox', 'source-state'])
def test_workspace_refuses_overlapping_source_and_storage_roles_before_io(tmp_path, monkeypatch, alias):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    state = tmp_path / 'outbox.sqlite3' if alias == 'state-outbox' else tmp_path / 'state.sqlite3'
    source = state if alias == 'source-state' else tmp_path / 'gui.ini'
    config = {'schema_version': 1, 'endpoint': ENDPOINT, 'user_id': 'alice',
              'outbox_path': str(tmp_path / 'outbox.sqlite3'), 'profiles': [
                  {'kind': 'workspace', 'state_path': str(state), 'source': {'path': str(source)}}]}
    with pytest.raises(ac.ConfigSyncError, match='overlap'):
        ac.SyncWorkspace(config)
    assert not list(tmp_path.glob('*.sqlite3'))


def test_historical_workspace_reset_is_idempotent_after_source_selection_changes(tmp_path, transport):
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    workspace.synchronize(options=OPTIONS)
    request = ac.SyncControlRequest('full_resync', operation_id='recover', discard_pending=True)
    original = workspace.control(request, options=OPTIONS)
    replacement = tmp_path / 'desktop/replacement.ini'
    replacement.write_text('[workspace]\ntheme=dark\n', encoding='utf-8')
    config['profiles'][0]['source']['path'] = str(replacement)
    changed = ac.SyncWorkspace(config)
    assert changed.capture() == 1
    before = len(transport['calls'])
    replay = changed.control(request, options=OPTIONS)
    assert replay.revision == original.revision and len(transport['calls']) == before
    assert changed.status()['outbox']['pending'] == 1


def test_retired_workspace_cannot_publish_a_generation_until_explicit_full_resync(tmp_path, transport):
    workspace, _ = build_workspace(tmp_path, 'desktop', theme='light')
    workspace.synchronize(options=OPTIONS)
    workspace.control(ac.SyncControlRequest('retire', peer_id='desktop'), options=OPTIONS)
    with pytest.raises(ac.FullResyncRequired):
        workspace.materialize(tmp_path / 'retired-cache')
    assert not (tmp_path / 'retired-cache').exists()


def test_workspace_path_authority_is_rechecked_after_each_rpc(tmp_path, transport):
    from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
    workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([tmp_path])
    workspace = ac.SyncWorkspace(config, path_policy=policy)
    def withdraw(_call, _reply):
        policy.set_client_roots([tmp_path / 'withdrawn'])
    transport['after'] = withdraw
    with pytest.raises(PathNotAllowedError):
        workspace.synchronize(options=OPTIONS)
    assert len(transport['calls']) == 1 and transport['calls'][0]['method'] == 'GET'


def test_seven_selected_domains_converge_without_activating_received_definitions(tmp_path, transport):
    reference = ac.SyncReference('local', 'script').to_dict()
    records = {'scripts': {'login.json': {'actions': []}}, 'locators': {'submit': {'name': 'Submit'}},
               'hotkeys': {'login': {'combo': 'ctrl+alt+1', 'script_path': reference}},
               'triggers': {'demo': {'kind': 'window', 'script_path': reference, 'repeat': False,
                                     'cooldown_seconds': 1, 'condition': {'title_substring': 'Demo',
                                                                         'case_sensitive': False}}},
               'address_book': {'office': {'host_id': 'office', 'server_url': 'https://signal.invalid',
                                            'label': 'Office', 'favorite': False, 'tags': []}},
               'settings': {'theme': {'value': 'dark'}}, 'workspace': {'theme': {'value': 'light'}}}
    configs = []
    for origin in ('desktop', 'laptop'):
        configs.append({'schema_version': 1, 'endpoint': ENDPOINT, 'user_id': 'alice',
            'outbox_path': str(tmp_path / (origin + '-outbox.sqlite3')), 'profiles': [
                {'kind': kind, 'state_path': str(tmp_path / (origin + '-adapters.sqlite3')),
                 'source': {'records': values if origin == 'desktop' else {}},
                 'bindings': {'local_values': {'script': 'scripts/login.json'}}} for kind, values in records.items()]})
    left, right = (ac.SyncWorkspace(config) for config in configs)
    assert left.synchronize(options=OPTIONS).delivered == 7
    assert right.synchronize(options=OPTIONS).state == 'ready'
    for kind in records:
        assert left.review(kind) == right.review(kind)
    generation = right.materialize(tmp_path / 'seven-cache')
    assert generation.file_count == 14
    for kind in ('hotkeys', 'triggers'):
        native = json.loads((generation.directory / (kind + '.json')).read_text(encoding='utf-8'))
        assert native[kind][0]['enabled'] is False
    assert right.capture() == 0


def test_resync_baseline_and_control_intent_roll_back_together_on_a_late_failure(tmp_path, transport):
    import sqlite3
    _workspace, config = build_workspace(tmp_path, 'desktop', theme='light')
    other = tmp_path / 'desktop/settings.json'
    other.write_text('{"retry":3}', encoding='utf-8')
    config['profiles'].append({'kind': 'settings', 'state_path': str(tmp_path / 'desktop/settings.sqlite3'),
                               'source': {'path': str(other)}})
    with sqlite3.connect(config['outbox_path']) as connection:
        connection.execute("CREATE TRIGGER reject_second_baseline BEFORE INSERT ON sync_workspace_baselines "
                           "WHEN NEW.kind='settings' BEGIN SELECT RAISE(ABORT,'controlled baseline failure'); END")
    with pytest.raises(ac.ConfigStoreError):
        ac.SyncWorkspace(config).control(ac.SyncControlRequest('full_resync', discard_pending=True), options=OPTIONS)
    with sqlite3.connect(config['outbox_path']) as connection:
        assert connection.execute('SELECT count(*) FROM sync_workspace_baselines').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM sync_controls').fetchone()[0] == 0
    assert not transport['calls']
