"""Commit a definition, reopen SQLite and demonstrate idempotent retry without networking."""
# pylint: disable=invalid-name  # reason: numbered example filenames follow the repository catalog
import argparse
import json
import tempfile
from pathlib import Path

import je_auto_control as ac


def exchange(path: Path) -> dict[str, object]:
    """Use one explicit store and retain its committed revision across restart."""
    bucket = ac.ConfigBucket('example', {'hotkeys': {'demo': {'combo': 'ctrl+k', 'last_modified': 1}}})
    store = ac.ConfigStore(path)
    try:
        revision = store.commit('example', bucket, base_revision=0, operation_id='example-edit')
    finally:
        store.close()
    reopened = ac.ConfigStore(path)
    try:
        retry = reopened.commit('example', bucket, base_revision=0, operation_id='example-edit')
        saved = reopened.get('example')
        saved_revision = saved.revision if saved is not None else None
    finally:
        reopened.close()
    return {'validated': revision == retry == saved_revision, 'revision': revision,
            'retried_revision': retry, 'reopened_revision': saved_revision, 'native_operations': []}


def main() -> None:
    """Default to a disposable store; persistence requires an explicit path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--state', type=Path)
    args = parser.parse_args()
    if args.validate and args.state:
        parser.error('--validate cannot write a persistent --state')
    with tempfile.TemporaryDirectory(prefix='ac-example-sync-') as folder:
        print(json.dumps(exchange(args.state or Path(folder) / 'config.sqlite')))


if __name__ == '__main__':
    main()
