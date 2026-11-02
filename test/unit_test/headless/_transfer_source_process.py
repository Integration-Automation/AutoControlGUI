"""An owned source process advances only its own grant clock, retaining bytes to test independent expiry."""
import json
import os
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

from headless.test_agent_transfer_payloads import FILES, manifest_source
from headless.test_agent_transfer_peer_security import approved_export
from je_auto_control.utils.agent_runtime import transfer_records, transfer_source
from je_auto_control.utils.rest_api.rest_server import RestApiServer


def write_private(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def advance_source_clock(runtime, exported, directory):
    clock = SimpleNamespace(time=lambda: exported['manifest']['expires'] + 1)
    transfer_records.time = clock
    transfer_source.time = clock
    source = runtime.transfers.source
    with runtime.store.connection() as connection:
        record = source.records.find(connection, exported['export_id'])
    write_private(directory / 'expired.json', {'now': clock.time(), 'expires': record['expires'],
        'private_chunks': source._cache.store.status(record['account'])['chunks']})


def main():
    config = json.load(sys.stdin)
    directory = Path(config['directory']).resolve()
    source_root = directory / 'source'
    source_root.mkdir()
    with manifest_source(source_root, named=True) as (runtime, task, _manifest, _bodies, users):
        server = RestApiServer(port=0, token='owned-source-process', user_store=users,
            agent_runtime=runtime, enable_audit=False, use_environment_users=False)
        try:
            server.start()
            token = users.rotate_token('owner')
            exported = approved_export(server, task, token=token,
                                       selection=[{'criterion': 0, 'names': list(FILES)}])
            write_private(directory / 'ready.json', {'pid': os.getpid(), 'parent_pid': os.getppid(),
                                                   'url': server.base_url,
                                                   'token': token, 'exported': exported})
            while not (directory / 'stop').exists():
                if (directory / 'expire').exists() and not (directory / 'expired.json').exists():
                    advance_source_clock(runtime, exported, directory)
                Event().wait(0.05)
        finally:
            server.stop()
            runtime.close()


if __name__ == '__main__':
    main()
