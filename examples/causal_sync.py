"""Causal conflict review and a durable local queue using controlled callbacks only."""
from pathlib import Path
from tempfile import TemporaryDirectory

from je_auto_control import (
    ConfigSyncError, FullResyncRequired, SyncEntry, SyncOperation, SyncOutbox, SyncPeers, SyncRetryPolicy,
    merge_entries,
)


def main() -> None:
    """Preserve both edits, resolve explicitly, then retry the same frozen request without HTTP or devices."""
    left=SyncEntry('settings','theme',{'value':'dark'},{'desktop':1},'edit-desktop','desktop')
    right=SyncEntry('settings','theme',{'value':'light'},{'laptop':1},'edit-laptop','laptop')
    conflict=merge_entries(left,right).conflict
    if conflict is None:
        raise ConfigSyncError('concurrent values were lost')
    resolved=left.evolve({'value':'chosen'},origin='desktop',operation_id='resolution',observed=(right,))
    if merge_entries(right,resolved).entry!=resolved:
        raise ConfigSyncError('explicit resolution did not cover both versions')
    peers=SyncPeers()
    peers.register('desktop',full_revision=1)
    peers.register('laptop',full_revision=0)
    peers.retire('laptop')
    try:
        peers.require_active('laptop')
    except FullResyncRequired:
        peer=peers.register('laptop',full_revision=1,full_resync=True)
    else:
        raise ConfigSyncError('retired peer resumed incrementally')
    with TemporaryDirectory(prefix='autocontrol-causal-sync-') as directory:
        path=Path(directory)/'outbox.sqlite3'
        operation=SyncOperation('delivery-1','https://synthetic.invalid','example','desktop',(resolved,))
        queue=SyncOutbox(path)
        queue.enqueue(operation)
        queue.prepare(operation,base_revision=0,bucket={'user_id':'example','revision':0,
                      'sections':{'settings':{'theme':{'value':'chosen','last_modified':0}}}})
        calls=[]
        def offline(value: SyncOperation) -> int:
            calls.append(value.to_dict())
            raise OSError('controlled offline')
        queue.flush(offline,endpoint=operation.endpoint,user_id=operation.user_id,
                    policy=SyncRetryPolicy(max_attempts=1,backoff=0))
        def recovered(value: SyncOperation) -> int:
            calls.append(value.to_dict())
            return 1
        result=SyncOutbox(path).flush(recovered,endpoint=operation.endpoint,user_id=operation.user_id)
        if calls[0]!=calls[1] or result.delivered!=1 or result.pending:
            raise ConfigSyncError('durable retry evidence did not match')
        print(f'conflict_alternatives=2; delivered={result.delivered}; pending={result.pending}; '
              f'peer_epoch={peer.epoch}; network_calls=0')


if __name__=='__main__':
    main()
