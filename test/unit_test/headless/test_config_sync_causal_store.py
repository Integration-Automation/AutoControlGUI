"""Authoritative causal CAS, guarded upgrades and acknowledged deletion fences."""
from dataclasses import replace

import pytest

from je_auto_control import ConfigBucket,ConfigRevisionConflict,ConfigStore,ConfigSyncError,SyncEntry


def actor(origin,mode='edit',*,epoch=0,peer_id=None,revision=None):
    from je_auto_control.utils.config_sync.causal_state import SyncActor
    return SyncActor(origin,epoch,mode,peer_id,revision)


def register(store,origin):
    state=store.get('alice')
    peers=state.peers
    record=peers.register(origin,full_revision=state.revision)
    candidate=state.with_peers(peers)
    store.commit('alice',candidate,base_revision=state.revision,operation_id=f'register-{origin}',
                 actor=actor(origin,'full_sync',epoch=record.epoch,revision=state.revision))
    return store.get('alice')


def test_causal_upgrade_preserves_plain_data_and_guards_old_writers(tmp_path):
    from je_auto_control.utils.config_sync.causal_store import CausalConfigStore
    path=tmp_path/'config.sqlite3'
    plain=ConfigStore(path)
    bucket=ConfigBucket('alice',{'settings':{'theme':{'value':'dark','last_modified':99}}})
    plain.commit('alice',bucket,base_revision=0,operation_id='plain')
    store=CausalConfigStore(path)
    before=store.get('alice')
    assert before.revision==1 and before.live_entries[0].value=={'value':'dark'}
    state=register(store,'desktop')
    assert state.revision==2 and state.live_entries==before.live_entries
    with pytest.raises(ConfigRevisionConflict):
        plain.commit('alice',bucket,base_revision=2,operation_id='old-writer')
    with pytest.raises(ConfigRevisionConflict):
        plain.put_legacy('alice',bucket.to_dict())
    assert store.get('alice').revision==2


def test_concurrent_edits_are_retained_and_missing_alternatives_are_rejected(tmp_path):
    from je_auto_control.utils.config_sync.causal_store import CausalConfigStore
    store=CausalConfigStore(tmp_path/'config.sqlite3')
    register(store,'desktop')
    base=register(store,'laptop')
    left=SyncEntry('settings','theme',{'value':'dark'},{'desktop':1},'left','desktop')
    right=SyncEntry('settings','theme',{'value':'light'},{'laptop':1},'right','laptop')
    store.commit('alice',base.with_entries((left,)),base_revision=base.revision,operation_id='left',actor=actor('desktop'))
    with pytest.raises(ConfigRevisionConflict):
        store.commit('alice',base.with_entries((right,)),base_revision=base.revision,
                     operation_id='stale-right',actor=actor('laptop'))
    current=store.get('alice')
    store.commit('alice',current.with_entries((right,)),base_revision=current.revision,
                 operation_id='right',actor=actor('laptop'))
    current=store.get('alice')
    assert len(current.conflicts)==1 and set(current.conflicts[0].origins)=={'desktop','laptop'}
    assert current.live_entries==()
    bad=replace(current,entries=(left,),committed={left.change_id:current.committed[left.change_id]})
    with pytest.raises(ConfigSyncError):
        store.commit('alice',bad,base_revision=current.revision,operation_id='drop-right',actor=actor('desktop'))
    assert store.get('alice').revision==current.revision


def test_collection_waits_for_acknowledgements_and_keeps_a_deletion_fence(tmp_path):
    from je_auto_control.utils.config_sync.causal_store import CausalConfigStore
    store=CausalConfigStore(tmp_path/'config.sqlite3')
    register(store,'desktop')
    state=register(store,'laptop')
    live=SyncEntry('settings','theme',{'value':'dark'},{'desktop':1},'initial','desktop')
    store.commit('alice',state.with_entries((live,)),base_revision=state.revision,
                 operation_id='initial',actor=actor('desktop'))
    state=store.get('alice')
    deleted=live.evolve(live.value,origin='desktop',operation_id='delete',is_deleted=True)
    deletion_revision=store.commit('alice',state.with_entries((deleted,)),base_revision=state.revision,
                                   operation_id='delete',actor=actor('desktop'))
    state=store.get('alice')
    assert state.collect().entries==(deleted,)
    for peer_id in ('desktop','laptop'):
        peers=state.peers
        peers.acknowledge(peer_id,deletion_revision,epoch=0)
        store.commit('alice',state.with_peers(peers),base_revision=state.revision,
                     operation_id=f'ack-{peer_id}',actor=actor(peer_id,'ack',revision=deletion_revision))
        state=store.get('alice')
    collected=state.collect()
    assert collected.entries==() and collected.fences[0].version==deleted.version
    store.commit('alice',collected,base_revision=state.revision,operation_id='collect',actor=actor('desktop','collect'))
    restored=store.get('alice').with_entries((live,))
    assert restored.live_entries==() and restored.entries==() and len(restored.fences)==1
    concurrent=SyncEntry('settings','theme',{'value':'light'},{'laptop':1},'offline-edit','laptop')
    assert len(restored.with_entries((concurrent,)).conflicts)==1


def test_retired_peer_needs_explicit_rejoin_and_old_epoch_stays_invalid(tmp_path):
    from je_auto_control.utils.config_sync.causal_store import CausalConfigStore
    from je_auto_control.utils.config_sync.peers import FullResyncRequired
    store=CausalConfigStore(tmp_path/'config.sqlite3')
    register(store,'desktop')
    state=register(store,'laptop')
    peers=state.peers
    peers.retire('laptop')
    store.commit('alice',state.with_peers(peers),base_revision=state.revision,
                 operation_id='retire',actor=actor('desktop','retire',peer_id='laptop'))
    state=store.get('alice')
    with pytest.raises(FullResyncRequired):
        store.commit('alice',state,base_revision=state.revision,operation_id='old-epoch',actor=actor('laptop'))
    peers=state.peers
    peers.register('laptop',full_revision=state.revision,full_resync=True)
    store.commit('alice',state.with_peers(peers),base_revision=state.revision,operation_id='rejoin',
                 actor=actor('laptop','full_sync',epoch=1,revision=state.revision))
    current=store.get('alice')
    assert current.peers.require_active('laptop',epoch=1).epoch==1
    with pytest.raises(FullResyncRequired):
        store.commit('alice',current,base_revision=current.revision,operation_id='stale-callback',actor=actor('laptop'))


def test_dedicated_causal_http_protocol_is_private_and_retries_are_idempotent(tmp_path):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    from je_auto_control.utils.config_sync.causal_state import CausalBucket
    path=tmp_path/'config.sqlite3'
    client=TestClient(create_app(config_store_path=path,shared_secret='synthetic-only',serve_web_viewer=False))
    assert client.get('/config/alice/causal').status_code==401 and not path.exists()
    headers={'X-Signaling-Secret':'synthetic-only'}
    response=client.get('/config/alice/causal',headers=headers)
    assert response.status_code==200 and response.json()['version']==3
    state=CausalBucket.from_dict(response.json()['bucket'])
    peers=state.peers
    peers.register('desktop',full_revision=0)
    body=state.with_peers(peers).to_dict()
    body['_actor']=actor('desktop','full_sync',revision=0).to_dict()
    envelope={'version':3,'base_revision':0,'operation_id':'register','bucket':body}
    first=client.put('/config/alice/causal',json=envelope,headers=headers)
    assert first.status_code==200 and first.json()['revision']==1
    repeated=client.put('/config/alice/causal',json=envelope,headers=headers)
    assert repeated.json()['revision']==1 and repeated.json()['bucket']['revision']==1
    assert client.get('/config/alice',headers=headers).status_code==409
