"""Durable queue identity, restart, bounded backoff and ownership during cancellation and overlap."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import pytest

from headless.test_config_sync_convergence import entry
from je_auto_control.utils.config_sync import ConfigStore, ConfigStoreError, ConfigSyncError
from je_auto_control.utils.config_sync.outbox import SyncOperation, SyncOutbox, SyncRetryPolicy


def operation(identifier='delivery-1', *, endpoint='https://sync.invalid', user_id='alice'):
    return SyncOperation(identifier,endpoint,user_id,'desktop',(entry('desktop','dark'),))


def test_changed_operation_cannot_replace_the_original(tmp_path):
    queue=SyncOutbox(tmp_path/'queue.sqlite3')
    original=operation()
    queue.enqueue(original)
    queue.enqueue(original)
    changed=replace(original,entries=(replace(original.entries[0],value={'value':'changed'}),))
    with pytest.raises(ConfigSyncError):
        queue.enqueue(changed)
    assert queue.pending(endpoint=original.endpoint,user_id='alice')==(original,)


def test_account_and_endpoint_namespaces_are_isolated(tmp_path):
    queue=SyncOutbox(tmp_path/'queue.sqlite3')
    originals=[operation(),operation(user_id='bob'),operation(endpoint='https://other.invalid')]
    for item in originals:
        queue.enqueue(item)
    for item in originals:
        assert queue.pending(endpoint=item.endpoint,user_id=item.user_id)==(item,)
    assert queue.pending(endpoint='HTTPS://SYNC.INVALID:443/',user_id='alice')==(originals[0],)


def test_bounded_views_and_drains_report_the_full_remaining_count(tmp_path):
    queue=SyncOutbox(tmp_path/'queue.sqlite3')
    first,second=operation('first'),operation('second')
    queue.enqueue(first)
    queue.enqueue(second)
    assert queue.pending(endpoint=first.endpoint,user_id='alice',limit=1)==(first,)
    assert queue.status(endpoint=first.endpoint,user_id='alice')['pending']==2
    report=queue.flush(lambda _item:1,endpoint=first.endpoint,user_id='alice',policy=SyncRetryPolicy(max_batch=1))
    assert report.delivered==1 and report.pending==1


def test_prepared_request_survives_restart_and_cannot_change_without_rejection(tmp_path):
    path=tmp_path/'queue.sqlite3'
    queue=SyncOutbox(path)
    original=operation()
    queue.enqueue(original)
    bucket={'user_id':'alice','revision':0,'sections':{}}
    prepared=queue.prepare(original,base_revision=0,bucket=bucket)
    bucket['revision']=99
    recovered=SyncOutbox(path).pending(endpoint=original.endpoint,user_id='alice')[0]
    assert recovered==prepared and recovered.prepared['bucket']['revision']==0
    with pytest.raises(ConfigSyncError):
        queue.prepare(original,base_revision=1,bucket={'user_id':'alice','revision':1,'sections':{}})
    wrong=replace(original,entries=(replace(original.entries[0],value={'value':'wrong'}),))
    with pytest.raises(ConfigSyncError):
        queue.reject_prepared(wrong,rejected_base=0)
    queue.reject_prepared(original,rejected_base=0)
    assert queue.pending(endpoint=original.endpoint,user_id='alice')[0].prepared is None


def test_pre_cancel_and_cancel_after_commit_keep_exact_pending_work(tmp_path):
    queue=SyncOutbox(tmp_path/'queue.sqlite3')
    first,second=operation('first'),operation('second')
    queue.enqueue(first)
    queue.enqueue(second)
    calls=[]
    cancelled=Event()
    cancelled.set()
    report=queue.flush(lambda item:calls.append(item) or 1,endpoint=first.endpoint,user_id='alice',
                       cancelled=cancelled.is_set)
    assert report.cancelled and calls==[]
    cancelled.clear()
    def send(item):
        calls.append(item)
        cancelled.set()
        return 1
    report=queue.flush(send,endpoint=first.endpoint,user_id='alice',cancelled=cancelled.is_set)
    assert report.delivered==1 and report.cancelled
    assert queue.pending(endpoint=first.endpoint,user_id='alice')==(second,)


def test_wrapped_interruption_is_not_an_offline_failure(tmp_path):
    queue=SyncOutbox(tmp_path/'queue.sqlite3')
    item=operation()
    queue.enqueue(item)
    def interrupted(_item):
        try:
            raise CancelledError()
        except CancelledError as cause:
            raise ConfigSyncError('wrapped interruption') from cause
    with pytest.raises(CancelledError):
        queue.flush(interrupted,endpoint=item.endpoint,user_id='alice')
    state=queue.status(endpoint=item.endpoint,user_id='alice')
    assert state['queued']==1 and state['offline']==0


def test_backoff_survives_reopen_without_sleeping(tmp_path):
    now=[100.0]
    path=tmp_path/'queue.sqlite3'
    queue=SyncOutbox(path,clock=lambda:now[0])
    item=operation()
    queue.enqueue(item)
    calls=[]
    def offline(received):
        calls.append(received)
        raise OSError('controlled offline')
    policy=SyncRetryPolicy(backoff=2,max_delay=10)
    report=queue.flush(offline,endpoint=item.endpoint,user_id='alice',policy=policy)
    assert report.failed==1 and len(calls)==1
    reopened=SyncOutbox(path,clock=lambda:now[0])
    assert reopened.status(endpoint=item.endpoint,user_id='alice')['next_attempt']==102
    report=reopened.flush(offline,endpoint=item.endpoint,user_id='alice',policy=policy)
    assert report.failed==0 and len(calls)==1
    now[0]=102
    assert reopened.flush(lambda _item:1,endpoint=item.endpoint,user_id='alice').delivered==1


def test_an_active_lease_prevents_a_second_sender(tmp_path):
    path=tmp_path/'queue.sqlite3'
    queue=SyncOutbox(path,clock=lambda:100.0)
    item=operation()
    queue.enqueue(item)
    entered,release=Event(),Event()
    def blocked(_item):
        entered.set()
        assert release.wait(5)
        return 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(queue.flush,blocked,endpoint=item.endpoint,user_id='alice')
        try:
            assert entered.wait(2)
            result=SyncOutbox(path,clock=lambda:100.0).flush(
                lambda _item:pytest.fail('live lease dispatched twice'),endpoint=item.endpoint,user_id='alice')
            assert result.delivered==0
        finally:
            release.set()
        assert future.result().delivered==1


def test_expired_sender_cannot_publish_a_new_owners_result(tmp_path):
    path=tmp_path/'queue.sqlite3'
    now=[100.0]
    queue=SyncOutbox(path,clock=lambda:now[0])
    item=operation()
    queue.enqueue(item)
    entered,release=Event(),Event()
    def blocked(_item):
        entered.set()
        assert release.wait(5)
        return 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(queue.flush,blocked,endpoint=item.endpoint,user_id='alice')
        try:
            assert entered.wait(2)
            now[0]=131
            assert SyncOutbox(path,clock=lambda:now[0]).flush(
                lambda _item:1,endpoint=item.endpoint,user_id='alice').delivered==1
        finally:
            release.set()
        assert future.result().delivered==0
    assert queue.status(endpoint=item.endpoint,user_id='alice')['confirmed_revision']==1


def test_foreign_database_is_not_modified(tmp_path):
    from je_auto_control import ConfigBucket
    path=tmp_path/'foreign.sqlite3'
    store=ConfigStore(path)
    store.commit('alice',ConfigBucket('alice'),base_revision=0,operation_id='original')
    with pytest.raises(ConfigStoreError):
        SyncOutbox(path).pending(endpoint='https://sync.invalid',user_id='alice')
    assert store.get('alice').revision==1


@pytest.mark.parametrize('endpoint',['https://user:password@sync.invalid','https://sync.invalid/?token=hidden',
                                     'file:///local','https://sync.invalid/#fragment'])
def test_credential_urls_are_rejected_before_queue_io(tmp_path,endpoint):
    path=tmp_path/'queue.sqlite3'
    with pytest.raises(ConfigSyncError):
        SyncOutbox(path).identity(endpoint,'alice')
    assert not path.exists()


def test_peer_acknowledgement_and_retirement_gate_collection():
    from je_auto_control.utils.config_sync.peers import FullResyncRequired,SyncPeers
    peers=SyncPeers()
    peers.register('desktop',full_revision=0)
    peers.register('laptop',full_revision=0)
    assert peers.can_collect(0) is False
    peers.acknowledge('desktop',3,epoch=0)
    assert peers.can_collect(3) is False
    peers.retire('laptop')
    assert peers.can_collect(3) is True
    restored=SyncPeers.from_dict(peers.to_dict())
    with pytest.raises(FullResyncRequired):
        restored.require_active('laptop')
    peers.retire('desktop')
    assert peers.can_collect(3) is False


def test_explicit_resolution_observes_both_alternatives_and_rejects_mutation():
    from je_auto_control.utils.config_sync.versions import merge_entries
    left,right=entry('desktop','dark'),entry('laptop','light')
    resolved=left.evolve({'value':'chosen'},origin='desktop',operation_id='resolution',observed=(right,))
    assert merge_entries(left,resolved).entry==resolved
    assert merge_entries(right,resolved).entry==resolved
    left.value['value']='changed outside the model'
    with pytest.raises(ConfigSyncError):
        merge_entries(left,right)


def test_namespace_epoch_is_stable_and_obsolete_edits_are_refused(tmp_path):
    from je_auto_control.utils.config_sync.peers import FullResyncRequired
    queue=SyncOutbox(tmp_path/'queue.sqlite3')
    current=replace(operation(),epoch=1)
    queue.enqueue(current)
    assert queue.identity(current.endpoint,'alice').epoch==1
    with pytest.raises(FullResyncRequired):
        queue.enqueue(replace(current,operation_id='obsolete',epoch=0))
    assert queue.pending(endpoint=current.endpoint,user_id='alice')==(current,)


def test_same_operation_cannot_change_a_json_boolean_into_a_number():
    from je_auto_control.utils.config_sync.versions import merge_entries
    left=replace(entry('desktop','dark'),value={'enabled':True})
    right=replace(left,value={'enabled':1})
    with pytest.raises(ConfigSyncError):
        merge_entries(left,right)


def test_full_sync_cannot_rewind_a_confirmed_peer():
    from je_auto_control.utils.config_sync.peers import SyncPeers
    peers=SyncPeers()
    peers.register('desktop',full_revision=3)
    with pytest.raises(ConfigSyncError):
        peers.register('desktop',full_revision=2,full_resync=True)
