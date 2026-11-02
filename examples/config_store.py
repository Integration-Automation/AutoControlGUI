"""Persistent revisions and safe operation retries using temporary local files only."""
from pathlib import Path
from tempfile import TemporaryDirectory

from je_auto_control import ConfigBucket, ConfigRevisionConflict, ConfigStore


def main() -> None:
    """Show restart, retry identity and stale-revision rejection without networking or device calls."""
    with TemporaryDirectory(prefix='autocontrol-config-store-') as directory:
        path=Path(directory)/'config.sqlite3'
        bucket=ConfigBucket('example')
        bucket.upsert('settings','theme',{'value':'dark'})
        first=ConfigStore(path).commit('example',bucket,base_revision=0,operation_id='first')
        reopened=ConfigStore(path)
        repeated=reopened.commit('example',bucket,base_revision=0,operation_id='first')
        if first!=repeated or reopened.get('example').revision!=first:
            raise RuntimeError('persistent retry evidence did not match')
        try:
            reopened.commit('example',bucket,base_revision=0,operation_id='stale')
        except ConfigRevisionConflict as conflict:
            print(f'committed={first}; repeated={repeated}; stale_conflict={conflict.current_revision}')
        else:
            raise RuntimeError('stale revision was accepted')


if __name__=='__main__':
    main()
