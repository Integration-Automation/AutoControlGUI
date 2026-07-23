"""Round-3 regression: the MCP HTTP transport must not be wedged by a peer.

The TLS handshake ran inside ``accept()`` on the single accept thread with no
bound, so one silent client blocked every other peer; and the request handler
had no read timeout, so a Content-Length underrun pinned a worker forever.
The handshake is now bounded in ``get_request`` and the handler declares a
finite ``timeout``.
"""
import datetime
import http.client
import ipaddress
import socket
import ssl
import time
from pathlib import Path

import pytest

from je_auto_control.utils.mcp_server import http_transport
from je_auto_control.utils.mcp_server.http_transport import (
    _MCPHttpHandler, start_mcp_http_server,
)

cryptography = pytest.importorskip("cryptography")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402


def test_handler_declares_a_finite_request_timeout():
    # Before the fix the handler inherited BaseHTTPRequestHandler.timeout=None
    # (no bound); a positive finite value is what closes a stalled body read.
    assert isinstance(_MCPHttpHandler.timeout, (int, float))
    assert _MCPHttpHandler.timeout > 0


def _server_ssl_context(tmp_path: Path) -> ssl.SSLContext:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mcp-test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]), critical=False)
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)  # NOSONAR python:S4423  # reason: loopback test server; PROTOCOL_TLS_SERVER negotiates modern TLS
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return ctx


def _insecure_client_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # NOSONAR S5527  # loopback test
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # NOSONAR S4830  # loopback self-signed test
    return ctx


def _post_initialize(host: str, port: int, ctx: ssl.SSLContext) -> int:
    body = ('{"jsonrpc":"2.0","id":1,"method":"initialize",'
            '"params":{"protocolVersion":"2025-06-18","capabilities":{}}}')
    conn = http.client.HTTPSConnection(host, port, context=ctx, timeout=6.0)
    try:
        conn.request("POST", "/mcp", body=body,
                     headers={"Content-Type": "application/json"})
        return conn.getresponse().status
    finally:
        conn.close()


def test_silent_tls_client_does_not_wedge_the_accept_thread(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(http_transport, "_HANDSHAKE_TIMEOUT", 0.5)
    server = start_mcp_http_server(
        host="127.0.0.1", port=0, ssl_context=_server_ssl_context(tmp_path))
    host, port = server.address
    silent = socket.create_connection((host, port), timeout=2.0)
    try:
        # Let the accept thread pick up the silent socket and enter the
        # (now time-boxed) handshake. Without the bound this wedges forever.
        time.sleep(0.3)
        status = _post_initialize(host, port, _insecure_client_context())
        assert status == 200
    finally:
        silent.close()
        server.stop(timeout=2.0)
