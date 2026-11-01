"""This package's HTTP servers bind without a reverse lookup of their own address."""
import ast
from pathlib import Path
import socket

import pytest

from je_auto_control.utils.http_headers import LocalThreadingHTTPServer

PACKAGE = Path(__file__).resolve().parents[3] / 'je_auto_control'
STOCK = {'HTTPServer', 'ThreadingHTTPServer'}


@pytest.fixture
def no_lookup(monkeypatch):
    def refused(*_args):
        raise AssertionError('a server start resolved its own name')
    monkeypatch.setattr(socket, 'getfqdn', refused)


def test_binding_records_the_bound_host_without_resolving_it(no_lookup):
    server = LocalThreadingHTTPServer(('127.0.0.1', 0), None)
    try:
        assert server.server_name == '127.0.0.1'
        assert server.server_port == server.server_address[1] > 0
    finally:
        server.server_close()


def _rest():
    from je_auto_control.utils.rest_api.rest_server import RestApiServer
    server = RestApiServer(host='127.0.0.1', port=0, enable_audit=False)
    server.start()
    return server.stop


def _exporter():
    from je_auto_control.utils.observability.exporter import PrometheusExporter
    exporter = PrometheusExporter(host='127.0.0.1', port=0)
    exporter.start()
    return exporter.stop


def _challenge():
    from je_auto_control.utils.tls_acme.challenge import HttpChallengeServer
    server = HttpChallengeServer(host='127.0.0.1', port=0)
    server.start()
    return server.stop


def _webhook():
    from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer
    server = WebhookTriggerServer()
    server.start('127.0.0.1', 0)
    return server.stop


@pytest.mark.parametrize('start', [_rest, _exporter, _challenge, _webhook], ids=lambda f: f.__name__[1:])
def test_each_server_starts_without_resolving_its_name(no_lookup, start):
    start()()


def test_the_mcp_http_server_uses_the_same_binding():
    from je_auto_control.utils.mcp_server.http_transport import _MCPHttpServer
    assert issubclass(_MCPHttpServer, LocalThreadingHTTPServer)


def _stock_uses(tree):
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Call):
            names.append(node.func)
        elif isinstance(node, ast.ClassDef):
            names.extend(node.bases)
        for name in names:
            label = name.attr if isinstance(name, ast.Attribute) else getattr(name, 'id', None)
            if label in STOCK:
                yield node.lineno


def test_no_module_builds_a_stock_http_server():
    offenders = []
    for path in PACKAGE.rglob('*.py'):
        if path.name == 'http_headers.py' and path.parent.name == 'utils':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        offenders.extend(f'{path.relative_to(PACKAGE)}:{line}' for line in _stock_uses(tree))
    assert offenders == [], 'use LocalThreadingHTTPServer from utils/http_headers.py: ' + ', '.join(offenders)
