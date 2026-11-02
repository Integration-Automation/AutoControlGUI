"""Causal server boundaries reject fabricated peer state and preserve durable deletion and retry evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3

import pytest

import je_auto_control as ac
from headless.test_config_sync_causal_store import actor, register


def seeded(tmp_path):
    store = ac.CausalConfigStore(tmp_path / 'config.sqlite3')
    register(store, 'desktop')
    state = register(store, 'laptop')
    entry = ac.SyncEntry('settings', 'theme', {'value': 'dark'}, {'desktop': 1}, 'initial', 'desktop')
    store.commit('alice', state.with_entries((entry,)), base_revision=state.revision,
                 operation_id='initial', actor=actor('desktop'))
    return store, store.get('alice'), entry


@pytest.mark.parametrize('mode', ['ack', 'retire', 'full_sync'])
def test_metadata_operations_cannot_smuggle_entry_changes(tmp_path, mode):
    store, current, entry = seeded(tmp_path)
    peers = current.peers
    if mode == 'ack':
        peers.acknowledge('desktop', current.revision, epoch=0)
        claim = actor('desktop', mode, revision=current.revision)
    elif mode == 'retire':
        peers.retire('laptop')
        claim = actor('desktop', mode, peer_id='laptop')
    else:
        peers.register('desktop', full_revision=current.revision, full_resync=True)
        claim = actor('desktop', mode, epoch=1, revision=current.revision)
    edited = entry.evolve({'value': 'smuggled'}, origin='desktop', operation_id='edit')
    candidate = current.with_peers(peers).with_entries((edited,))
    with pytest.raises(ac.ConfigSyncError):
        store.commit('alice', candidate, base_revision=current.revision, operation_id=mode, actor=claim)
    assert store.get('alice') == current


@pytest.mark.parametrize('change', ['other-ack', 'future-ack', 'forget-peer', 'retire-peer', 'forged-revision'])
def test_actor_cannot_forge_server_owned_metadata(tmp_path, change):
    store, current, entry = seeded(tmp_path)
    peers = current.peers
    claim = actor('desktop')
    if change == 'other-ack':
        peers.acknowledge('laptop', current.revision, epoch=0)
        candidate = current.with_peers(peers)
    elif change == 'future-ack':
        peers.acknowledge('desktop', current.revision + 1, epoch=0)
        candidate = current.with_peers(peers)
        claim = actor('desktop', 'ack', revision=current.revision + 1)
    elif change == 'forget-peer':
        raw = peers.to_dict()
        raw['peers'] = [item for item in raw['peers'] if item['peer_id'] != 'laptop']
        candidate = current.with_peers(ac.SyncPeers.from_dict(raw))
    elif change == 'retire-peer':
        peers.retire('laptop')
        candidate = current.with_peers(peers)
    else:
        candidate = replace(current, committed={entry.change_id: 1})
    with pytest.raises(ac.ConfigSyncError):
        store.commit('alice', candidate, base_revision=current.revision, operation_id=change, actor=claim)
    assert store.get('alice') == current


@pytest.mark.parametrize('change', [
    'other-origin', 'unseen-version', 'counter-rewind', 'operation-reuse', 'payload-fork'])
def test_entry_changes_require_an_honest_origin_and_causal_floor(tmp_path, change):
    store, current, entry = seeded(tmp_path)
    args = dict(section='settings', entry_id='theme', value={'value': 'new'}, version={'desktop': 2},
                operation_id='new', origin='desktop')
    if change == 'other-origin':
        args.update(origin='laptop', version={'laptop': 1})
    elif change == 'unseen-version':
        args['version'] = {'desktop': 2, 'unknown': 99}
    elif change == 'counter-rewind':
        args['version'] = {'desktop': 1}
    elif change == 'operation-reuse':
        args['operation_id'] = 'initial'
    else:
        args.update(version=entry.version, operation_id=entry.operation_id)
    proposed = ac.SyncEntry(**args)
    with pytest.raises(ac.ConfigSyncError):
        candidate = current.with_entries((proposed,))
        store.commit('alice', candidate, base_revision=current.revision, operation_id=change, actor=actor('desktop'))
    assert store.get('alice') == current


def test_receipts_survive_retirement_restart_and_later_writes(tmp_path):
    store, current, entry = seeded(tmp_path)
    candidate = current.with_entries((entry.evolve({'value': 'light'}, origin='desktop', operation_id='edit'),))
    arguments = dict(base_revision=current.revision, operation_id='delivered', actor=actor('desktop'))
    receipt = store.commit('alice', candidate, **arguments)
    later = store.get('alice')
    peers = later.peers
    peers.retire('desktop')
    store.commit('alice', later.with_peers(peers), base_revision=later.revision,
                 operation_id='retire', actor=actor('laptop', 'retire', peer_id='desktop'))
    reopened = ac.CausalConfigStore(tmp_path / 'config.sqlite3')
    assert reopened.commit('alice', candidate, **arguments) == receipt
    with pytest.raises(ac.ConfigRevisionConflict):
        reopened.commit('alice', current, **arguments)
    assert reopened.get('alice').revision == receipt + 1


def test_collection_reclaims_payload_but_retains_floor_across_restart_and_restore(tmp_path):
    store, current, entry = seeded(tmp_path)
    deleted = entry.evolve(entry.value, origin='desktop', operation_id='delete', is_deleted=True)
    revision = store.commit('alice', current.with_entries((deleted,)), base_revision=current.revision,
                            operation_id='delete', actor=actor('desktop'))
    for origin in ('desktop', 'laptop'):
        current = store.get('alice')
        peers = current.peers
        peers.acknowledge(origin, revision, epoch=0)
        store.commit('alice', current.with_peers(peers), base_revision=current.revision,
                     operation_id='ack-' + origin, actor=actor(origin, 'ack', revision=revision))
    current = store.get('alice')
    store.commit('alice', current.collect(), base_revision=current.revision,
                 operation_id='collect', actor=actor('desktop', 'collect'))
    with sqlite3.connect(tmp_path / 'config.sqlite3') as connection:
        raw = json.loads(connection.execute('SELECT body FROM config_buckets').fetchone()[0])
    assert raw['entries'] == [] and 'value' not in raw['fences'][0]
    current = ac.CausalConfigStore(tmp_path / 'config.sqlite3').get('alice')
    assert current.with_entries((entry, deleted)).entries == ()
    concurrent = ac.SyncEntry('settings', 'theme', {'value': 'offline'}, {'laptop': 1}, 'offline', 'laptop')
    conflict = current.with_entries((concurrent,))
    store.commit('alice', conflict, base_revision=current.revision, operation_id='offline', actor=actor('laptop'))
    current = store.get('alice')
    assert len(current.conflicts) == 1 and current.collect() == current
    resolved = concurrent.evolve({'value': 'restored'}, origin='laptop', operation_id='restore', observed=(deleted,))
    store.commit('alice', current.with_entries((resolved,)), base_revision=current.revision,
                 operation_id='restore', actor=actor('laptop'))
    final = store.get('alice')
    assert final.live_entries == (resolved,) and final.fences == () and final.conflicts == ()


def test_concurrent_store_instances_share_one_atomic_cas_boundary(tmp_path):
    store, current, _entry = seeded(tmp_path)
    def write(origin):
        entry = ac.SyncEntry('settings', 'other', {'value': origin}, {origin: 1}, origin, origin)
        try:
            return ac.CausalConfigStore(tmp_path / 'config.sqlite3').commit(
                'alice', current.with_entries((entry,)), base_revision=current.revision,
                operation_id=origin, actor=actor(origin))
        except ac.ConfigRevisionConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ('desktop', 'laptop')))
    assert outcomes.count('conflict') == 1 and outcomes.count(current.revision + 1) == 1
    assert store.get('alice').revision == current.revision + 1


def test_legacy_tombstones_never_expire_during_upgrade_and_opaque_data_is_not_lost(tmp_path):
    path = tmp_path / 'config.sqlite3'
    legacy = ac.ConfigStore(path)
    legacy.put_legacy('alice', ac.ConfigBucket('alice', {'settings': {
        'old': {'deleted': True, 'last_modified': 0, 'value': 'previous'}}}).to_dict())
    state = ac.CausalConfigStore(path).get('alice')
    assert state.entries[0].is_deleted and state.live_entries == ()
    assert state.entries[0].value == {'value': 'previous'}
    legacy.put_legacy('bob', {'user_id': 'bob', 'opaque': {'important': True}})
    with pytest.raises(ac.ConfigSyncError):
        ac.CausalConfigStore(path).get('bob')
    assert legacy.get_document('bob')['opaque'] == {'important': True}


def test_causal_commands_share_existing_mcp_builder_and_private_path_guards(tmp_path, monkeypatch):
    from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    state = ac.CausalBucket('alice')
    peers = state.peers
    peers.register('desktop', full_revision=0)
    body = state.with_peers(peers).to_dict()
    body['_actor'] = actor('desktop', 'full_sync', revision=0).to_dict()
    args = dict(path=str(tmp_path / 'config.sqlite3'), user_id='alice', bucket=body,
                base_revision=0, operation_id='register')
    action = ['AC_config_store_commit', args]
    assert step_to_action(action_to_step(action)) == action
    ac.executor.execute_action([action], raise_on_error=True)
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    assert tools['ac_config_store_commit'].handler(**args) == {'version': 3, 'revision': 1, 'cas': True}
    read = tools['ac_config_store_get'].handler(path=args['path'], user_id='alice')
    assert read['version'] == 3 and read['bucket']['revision'] == 1


@pytest.mark.parametrize('bad', [[], {}, {'schema_version': 1}, {'schema_version': True}])
def test_malformed_causal_documents_fail_with_typed_errors(bad):
    with pytest.raises(ac.ConfigSyncError):
        ac.CausalBucket.from_dict(bad)
    with pytest.raises(ac.ConfigSyncError):
        ac.SyncActor.from_dict(bad)


def test_snapshots_detect_mapping_mutation_and_copy_inputs():
    state = ac.CausalBucket('alice')
    peers = state.peers
    peers.register('desktop', full_revision=0)
    populated = state.with_peers(peers)
    peers.retire('desktop')
    assert populated.peers.require_active('desktop').retired is False
    populated.peer_state['peers'][0]['epoch'] = 999
    with pytest.raises(ac.ConfigSyncError):
        populated.to_dict()


@pytest.mark.parametrize('change', ['protocol-bool', 'extra', 'missing-actor', 'bad-mode', 'bad-revision', 'account'])
def test_http_rejects_malformed_or_cross_account_commits_without_creating_accounts(tmp_path, change):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    path = tmp_path / 'config.sqlite3'
    client = TestClient(create_app(config_store_path=path, serve_web_viewer=False))
    bucket = ac.CausalBucket('alice').to_dict()
    bucket['_actor'] = actor('desktop', 'full_sync', revision=0).to_dict()
    envelope = dict(version=3, base_revision=0, operation_id='bad', bucket=bucket)
    if change == 'protocol-bool':
        envelope['version'] = True
    elif change == 'extra':
        envelope['unknown'] = True
    elif change == 'missing-actor':
        del bucket['_actor']
    elif change == 'bad-mode':
        bucket['_actor']['mode'] = []
    elif change == 'bad-revision':
        envelope['base_revision'] = True
    else:
        bucket['user_id'] = 'bob'
    assert client.put('/config/alice/causal', json=envelope).status_code == 400
    assert ac.CausalConfigStore(path).get('alice').revision == 0
    assert ac.CausalConfigStore(path).get('bob').revision == 0
