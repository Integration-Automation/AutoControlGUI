"""Durable peer registration, collection and full resync against a temporary loopback-only HTTP server."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Iterator

from je_auto_control import (
    CausalBucket, CausalConfigStore, CausalSyncClient, ConfigRevisionConflict, ConfigSyncError,
    FullResyncRequired, SyncActor, SyncControlRequest, SyncEntry, SyncOperation, SyncOutbox,
)


@contextmanager
def loopback_server(store: CausalConfigStore) -> Iterator[str]:
    """Provide a minimal demonstration server on an ephemeral local port; production uses the authenticated routes."""
    class Handler(BaseHTTPRequestHandler):
        """Serve the example account only, without filesystem or GUI access."""

        def do_GET(self) -> None:  # pylint: disable=invalid-name  # reason: stdlib HTTP handler contract
            """Return the complete example snapshot."""
            if self.path != '/config/example/causal':
                self.send_error(404)
                return
            self.reply(200, {'version': 3, 'bucket': store.get('example').to_dict()})

        def do_PUT(self) -> None:  # pylint: disable=invalid-name  # reason: stdlib HTTP handler contract
            """Commit a complete actor request and retain the original revision on retry."""
            if self.path != '/config/example/causal':
                self.send_error(404)
                return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2 * 1024 * 1024:
                self.send_error(413)
                return
            try:
                body = json.loads(self.rfile.read(size))
                raw = dict(body['bucket'])
                actor = SyncActor.from_dict(raw.pop('_actor'))
                revision = store.commit('example', CausalBucket.from_dict(raw), base_revision=body['base_revision'],
                                         operation_id=body['operation_id'], actor=actor)
            except ConfigRevisionConflict as error:
                self.reply(409, {'detail': {'code': error.code, 'revision': error.current_revision}})
            except FullResyncRequired:
                self.reply(409, {'detail': {'code': 'full_resync_required'}})
            except (ValueError, KeyError, TypeError, ConfigSyncError):
                self.send_error(400)
            else:
                self.reply(200, {'version': 3, 'revision': revision, 'bucket': store.get('example').to_dict()})

        def reply(self, status: int, body: dict[str, object]) -> None:
            """Write one bounded JSON response."""
            encoded = json.dumps(body).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *args: object) -> None:
            """Keep the controlled example output concise."""

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            worker.join(timeout=5)


def workflow(directory: Path, endpoint: str) -> None:
    """Queue offline work, join, collect a deletion, then explicitly retire an obsolete local generation."""
    queue = SyncOutbox(directory / 'outbox.sqlite3')
    queue.identity(endpoint, 'example', origin='desktop')
    client = CausalSyncClient(endpoint, user_id='example')
    entry = SyncEntry('settings', 'theme', {'value': 'dark'}, {'desktop': 1}, 'theme', 'desktop')
    queue.enqueue(SyncOperation('theme', endpoint, 'example', 'desktop', (entry,)))
    client.control(queue, SyncControlRequest('register', operation_id='join'))
    client.flush(queue)
    deleted = entry.evolve(entry.value, origin='desktop', operation_id='delete', is_deleted=True)
    queue.enqueue(SyncOperation('delete', endpoint, 'example', 'desktop', (deleted,)))
    client.flush(queue)
    client.control(queue, 'ack')
    client.control(queue, 'collect')
    client.control(queue, 'retire', peer_id='desktop')
    pending = deleted.evolve({'value': 'offline'}, origin='desktop', operation_id='obsolete')
    queue.enqueue(SyncOperation('obsolete', endpoint, 'example', 'desktop', (pending,)))
    request = SyncControlRequest('full_resync', operation_id='recover', discard_pending=True)
    result = client.control(queue, request)
    replay = client.control(SyncOutbox(directory / 'outbox.sqlite3'), request)
    state = queue.status(endpoint=endpoint, user_id='example')
    print(f'full_resync_revision={result.revision}; replay_revision={replay.revision}; '
          f'epoch={queue.identity(endpoint, "example").epoch}; retired={state["retired"]}; '
          f'pending={state["pending"]}; external_calls=0')


def main() -> None:
    """Run with temporary SQLite files and loopback requests; apply no configuration and execute no scripts."""
    with TemporaryDirectory(prefix='autocontrol-peer-control-') as temporary:
        directory = Path(temporary)
        with loopback_server(CausalConfigStore(directory / 'server.sqlite3')) as endpoint:
            workflow(directory, endpoint)


if __name__ == '__main__':
    main()
