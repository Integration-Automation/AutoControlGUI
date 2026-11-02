"""Persistent per-account revision commits across restart, races and uncertain retries."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from je_auto_control.utils.config_sync import ConfigBucket


def bucket(user='alice', value='first'):
    return ConfigBucket(user, {'hotkeys': {'one': {'combo': value, 'last_modified': 1.0}}})


def test_reopen_preserves_bucket(tmp_path):
    from je_auto_control.utils.config_sync.store import ConfigStore
    path=tmp_path/'config.sqlite3'
    committed_revision=ConfigStore(path).commit('alice',bucket(),base_revision=0,operation_id='first')
    reopened=ConfigStore(path)
    assert reopened.get('alice').revision==committed_revision
    assert reopened.get('alice').sections==bucket().sections


def test_stale_revision_conflicts(tmp_path):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    client=TestClient(create_app(config_store_path=tmp_path/'config.sqlite3',serve_web_viewer=False))
    envelope={'version':2,'base_revision':0,'operation_id':'original','bucket':bucket().to_dict()}
    original=client.put('/config/alice',json=envelope)
    assert original.status_code==200
    stale_response=client.put('/config/alice',json={**envelope,'operation_id':'stale'})
    assert stale_response.status_code==409
    assert client.get('/config/alice').json()['revision']==original.json()['revision']


def test_operation_retry_is_idempotent(tmp_path):
    from je_auto_control.utils.config_sync.store import ConfigStore
    store=ConfigStore(tmp_path/'config.sqlite3')
    original=store.commit('alice',bucket(),base_revision=0,operation_id='original')
    store.commit('alice',bucket(value='second'),base_revision=original,operation_id='later')
    repeated=store.commit('alice',bucket(),base_revision=0,operation_id='original')
    assert repeated==original
    assert store.get('alice').revision==original+1
    assert store.get('alice').sections==bucket(value='second').sections


def test_two_connections_cannot_commit_the_same_base(tmp_path):
    from je_auto_control.utils.config_sync.store import ConfigRevisionConflict,ConfigStore
    path=tmp_path/'config.sqlite3'
    def commit(index):
        try:
            return ConfigStore(path).commit('alice',bucket(value=str(index)),base_revision=0,operation_id=f'op-{index}')
        except ConfigRevisionConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(commit,range(2)))
    assert sorted(map(str,replies))==['1','conflict']


def test_retry_id_is_bound_to_account_and_content(tmp_path):
    from je_auto_control.utils.config_sync.store import ConfigRevisionConflict,ConfigStore
    store=ConfigStore(tmp_path/'config.sqlite3')
    assert store.commit('alice',bucket(),base_revision=0,operation_id='same')==1
    with pytest.raises(ConfigRevisionConflict):
        store.commit('alice',bucket(value='changed'),base_revision=0,operation_id='same')
    assert store.commit('bob',bucket('bob'),base_revision=0,operation_id='same')==1
    assert store.get('nobody') is None


def test_default_store_path_is_resolved_only_on_use(tmp_path,monkeypatch):
    from je_auto_control.utils.config_sync.store import ConfigStore
    first=tmp_path/'first.sqlite3'
    second=tmp_path/'second.sqlite3'
    monkeypatch.setenv('AUTOCONTROL_CONFIG_STORE',str(first))
    store=ConfigStore()
    assert not first.exists()
    monkeypatch.setenv('AUTOCONTROL_CONFIG_STORE',str(second))
    store.commit('alice',bucket(),base_revision=0,operation_id='first')
    assert second.is_file() and not first.exists()


def test_server_reopen_and_retry_do_not_overwrite_a_later_commit(tmp_path):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    path=tmp_path/'config.sqlite3'
    request={'version':2,'base_revision':0,'operation_id':'first','bucket':bucket().to_dict()}
    first=TestClient(create_app(config_store_path=path,serve_web_viewer=False))
    assert first.put('/config/alice',json=request).json()['revision']==1
    second=TestClient(create_app(config_store_path=path,serve_web_viewer=False))
    assert second.get('/config/alice').json()['revision']==1
    assert second.put('/config/alice',json={**request,'operation_id':'second','base_revision':1,
                                          'bucket':bucket(value='second').to_dict()}).json()['revision']==2
    assert second.put('/config/alice',json=request).json()['revision']==1
    assert second.get('/config/alice').json()['sections']==bucket(value='second').sections


def test_private_routes_are_lazy_and_legacy_requires_explicit_opt_in(tmp_path):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    path=tmp_path/'config.sqlite3'
    app=create_app(config_store_path=path,shared_secret='synthetic-test',serve_web_viewer=False)
    assert not path.exists()
    client=TestClient(app)
    assert client.get('/config/alice').status_code==401
    assert not path.exists()
    headers={'X-Signaling-Secret':'synthetic-test'}
    assert client.put('/config/alice',json=bucket().to_dict(),headers=headers).status_code==428
    assert not path.exists()
    compatible=TestClient(create_app(config_store_path=path,allow_legacy_config_writes=True,
                                    shared_secret='synthetic-test',serve_web_viewer=False))
    assert compatible.put('/config/alice',json=bucket().to_dict(),headers=headers).json()['revision']==1
    reply=compatible.get('/config/alice',headers=headers)
    assert reply.headers['X-Autocontrol-Config-CAS']=='legacy-enabled'
    assert reply.json()['revision']==1


@pytest.mark.parametrize('invalid',[
    {'version':2.0},{'base_revision':True},{'base_revision':-1},{'operation_id':''},
    {'bucket':{'user_id':'bob'}},{'bucket':{'user_id':'alice','sections':[]}},
    {'bucket':{'user_id':'alice','revision':True}},
])
def test_version_two_rejects_invalid_input_before_database_io(tmp_path,invalid):
    pytest.importorskip('fastapi')
    from fastapi.testclient import TestClient
    from je_auto_control.utils.remote_desktop.signaling_server import create_app
    path=tmp_path/'config.sqlite3'
    client=TestClient(create_app(config_store_path=path,serve_web_viewer=False))
    body={'version':2,'base_revision':0,'operation_id':'first','bucket':bucket().to_dict()}
    assert client.put('/config/alice',json={**body,**invalid}).status_code==400
    assert not path.exists()


def test_capacity_and_independent_reads_survive_reopen(tmp_path):
    from je_auto_control.utils.config_sync.store import ConfigStore,ConfigStoreFull
    path=tmp_path/'config.sqlite3'
    store=ConfigStore(path,max_users=1)
    original=bucket()
    store.commit('alice',original,base_revision=0,operation_id='first')
    original.sections.clear()
    read=store.get('alice')
    assert read.sections
    read.sections.clear()
    assert store.get('alice').sections
    with pytest.raises(ConfigStoreFull):
        ConfigStore(path,max_users=1).commit('bob',bucket('bob'),base_revision=0,operation_id='first')
    assert store.get('bob') is None


@pytest.mark.parametrize('reply',[None,[],{'version':2.0,'revision':1},{'version':2,'revision':True}])
def test_client_rejects_unconfirmed_conditional_commits(reply):
    from unittest.mock import patch
    from je_auto_control.utils.config_sync import ConfigSyncClient,ConfigSyncError
    client=ConfigSyncClient('https://synthetic.invalid',user_id='alice')
    with patch.object(client,'_request',return_value=reply):
        with pytest.raises(ConfigSyncError):
            client.push(bucket(),operation_id='first')


def test_conditional_client_never_writes_an_unsupported_legacy_server(monkeypatch):
    from urllib.parse import urlsplit
    pytest.importorskip('fastapi')
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from je_auto_control.utils.config_sync import ConfigSyncClient,ConfigSyncError
    writes=[]
    old=FastAPI()
    @old.put('/config/{user_id}')
    def blind_put(user_id:str,body:dict):
        writes.append((user_id,body))
        return {'ok':True}
    transport=TestClient(old)
    def perform(call):
        response=transport.request(call['method'],urlsplit(call['url']).path,
                                   content=call['body'],headers=call['headers'])
        return {'status':response.status_code,'text':response.text,'headers':dict(response.headers)}
    monkeypatch.setattr('je_auto_control.utils.http_client.http_client.perform_call',perform)
    with pytest.raises(ConfigSyncError):
        ConfigSyncClient('https://synthetic.invalid',user_id='alice').push(bucket(),operation_id='first')
    assert writes==[]
