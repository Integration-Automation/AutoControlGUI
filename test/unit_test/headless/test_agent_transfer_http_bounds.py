"""Transfer HTTP requests and success/error replies enforce per-call bounds before decoding."""
from contextlib import contextmanager
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.error import URLError

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transport import request_json
from je_auto_control.utils.http_client import http_client


@contextmanager
def wire_server(body, *, status=200):
    received = []

    class Reply(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, dict(self.headers)))
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Reply)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', received
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


@pytest.mark.parametrize('status', [200, 400, 302])
@pytest.mark.parametrize('path', ['/agent/transfer', '/agent/transfer/peer',
                                '/proxy/v1/agent/transfer', '/proxy/v1/agent/transfer/peer'])
def test_transfer_refuses_oversized_success_and_error_bodies_over_real_http(status, path):
    body = b'{"padding":"' + b'x' * (1024 * 1024 - 13) + b'"}'
    assert len(body) == 1024 * 1024 + 1
    with wire_server(body, status=status) as (url, _received):
        with pytest.raises(URLError, match='1048576'):
            request_json(url + path, body={}, token='owned-source-token', timeout=3)


def test_transfer_reply_bound_does_not_reduce_ordinary_http_reply_limit():
    text = 'x' * (1024 * 1024 + 10)
    body = json.dumps({'padding': text}).encode()
    with wire_server(body) as (url, _received):
        assert request_json(url + '/ordinary', body={}, timeout=3) == {'padding': text}


@pytest.mark.parametrize('path', ['/agent/transfer', '/agent/transfer/peer',
                                '/proxy/v1/agent/transfer', '/proxy/v1/agent/transfer/peer'])
def test_transfer_refuses_large_request_before_any_network_dispatch(path):
    with wire_server(b'{}') as (url, received):
        with pytest.raises(AgentTaskError, match='request'):
            request_json(url + path, body={'padding': 'x' * (1024 * 1024)}, timeout=3)
        assert received == []


def test_per_call_response_guard_limits_the_actual_reader_allocation(monkeypatch):
    reads = []

    class Response(io.BytesIO):
        status = 200
        headers = {}

        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    # Only the socket response is replaced: the actual client must enforce its allocation bound.
    monkeypatch.setattr(http_client._NO_REDIRECT_OPENER, 'open',
                        lambda _request, timeout: Response(b'x' * (1024 * 1024 + 1)))
    call = http_client.build_call('http://127.0.0.1:1/agent/transfer/peer')
    call.update(follow_redirects=False, max_response_bytes=1024 * 1024)
    with pytest.raises(URLError, match='1048576'):
        http_client.urllib_transport(call)
    assert reads == [1024 * 1024 + 1]
