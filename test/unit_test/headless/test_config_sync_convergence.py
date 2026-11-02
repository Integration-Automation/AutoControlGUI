"""Causal changes preserve conflicts and durable retry identity without wall-clock winners."""
from dataclasses import replace

import pytest


def entry(origin, value, stamp=1.0, version=None):
    from je_auto_control.utils.config_sync.versions import SyncEntry
    return SyncEntry('settings','theme',{'value':value,'last_modified':stamp},
                     {origin:1} if version is None else version,f'edit-{origin}',origin)


def test_parallel_edits_preserve_conflict():
    from je_auto_control.utils.config_sync.versions import merge_entries
    left=entry('desktop','dark')
    right=entry('laptop','light')
    conflict=merge_entries(left,right).conflict
    assert conflict.local==left and conflict.remote==right
    assert merge_entries(right,left).conflict.local==right


def test_restart_retries_outbox(tmp_path):
    from je_auto_control.utils.config_sync.outbox import SyncOperation,SyncOutbox,SyncRetryPolicy
    operation=SyncOperation('delivery-1','https://sync.invalid','alice','desktop',(entry('desktop','dark'),))
    path=tmp_path/'outbox.sqlite3'
    original=SyncOutbox(path)
    original.enqueue(operation)
    calls=[]
    def offline(received):
        calls.append(received)
        raise OSError('controlled offline')
    policy=SyncRetryPolicy(max_attempts=1,backoff=0)
    original.flush(offline,endpoint=operation.endpoint,user_id='alice',policy=policy)
    reopened=SyncOutbox(path)
    assert reopened.pending(endpoint=operation.endpoint,user_id='alice')==(operation,)
    def recovered(received):
        calls.append(received)
        return 1
    report=reopened.flush(recovered,endpoint=operation.endpoint,user_id='alice',policy=policy)
    assert report.delivered==1
    assert calls==[operation,operation]
    assert reopened.pending(endpoint=operation.endpoint,user_id='alice')==()


def test_retired_peer_requires_full_sync():
    from je_auto_control.utils.config_sync.peers import FullResyncRequired,SyncPeers
    peers=SyncPeers()
    peers.register('laptop',full_revision=0)
    peers.retire('laptop')
    with pytest.raises(FullResyncRequired):
        peers.require_active('laptop')
    with pytest.raises(FullResyncRequired):
        peers.register('laptop',full_revision=10)
    record=peers.register('laptop',full_revision=10,full_resync=True)
    assert record.acknowledged_revision==10 and record.epoch==1
    assert peers.require_active('laptop',epoch=1)==record


def test_clock_skew_does_not_choose_winner():
    from je_auto_control.utils.config_sync.versions import merge_entries
    left=entry('desktop','dark',stamp=9999999999)
    right=entry('laptop','light',stamp=0)
    assert merge_entries(left,right).conflict is not None
    swapped=merge_entries(replace(left,value={**left.value,'last_modified':0}),
                          replace(right,value={**right.value,'last_modified':9999999999}))
    wall_clock_does_not_change_merge=swapped.conflict is not None
    assert wall_clock_does_not_change_merge is True
    tombstone=replace(right,version={'desktop':1,'laptop':2},is_deleted=True)
    assert merge_entries(left,tombstone).entry==tombstone
    assert tombstone.is_deleted is True
