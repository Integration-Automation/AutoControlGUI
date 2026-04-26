"""End-to-end TLS tests using a self-signed loopback certificate."""
import datetime
import ipaddress
import socket
import ssl
import time
from pathlib import Path
from typing import Tuple

import pytest

cryptography = pytest.importorskip("cryptography")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from je_auto_control.utils.remote_desktop import (
    RemoteDesktopHost, RemoteDesktopViewer,
)
from je_auto_control.utils.remote_desktop.protocol import AuthenticationError


def _wait_until(predicate, timeout: float = 2.0,
                interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _generate_self_signed(tmp_path: Path) -> Tuple[Path, Path]:
    """Write a self-signed cert + key for ``127.0.0.1`` to ``tmp_path``."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "remote-desktop-test"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def _server_context(cert_path: Path, key_path: Path) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return ctx


def _trusting_client_context(ca_path: Path) -> ssl.SSLContext:
    """Verifying client context that trusts only the supplied test CA cert."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(cafile=str(ca_path))
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _insecure_client_context() -> ssl.SSLContext:
    """Self-signed loopback test context — verification deliberately off."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # NOSONAR S5527  # loopback self-signed test
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # NOSONAR S4830  # loopback self-signed test
    return ctx


def _start_tls_host(tmp_path: Path) -> Tuple[RemoteDesktopHost, Path, Path]:
    cert_path, key_path = _generate_self_signed(tmp_path)
    server_ctx = _server_context(cert_path, key_path)
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"tls-frame",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="111111111", ssl_context=server_ctx,
    )
    host.start()
    return host, cert_path, key_path


def test_tls_round_trip_with_trusting_client(tmp_path):
    host, cert_path, _ = _start_tls_host(tmp_path)
    try:
        client_ctx = _trusting_client_context(cert_path)
        received = []
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            on_frame=received.append,
            ssl_context=client_ctx,
        )
        viewer.connect(timeout=2.0)
        assert _wait_until(lambda: len(received) >= 1, timeout=2.0)
        assert all(frame == b"tls-frame" for frame in received)
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_tls_round_trip_with_insecure_client(tmp_path):
    host, _, _ = _start_tls_host(tmp_path)
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            ssl_context=_insecure_client_context(),
        )
        viewer.connect(timeout=2.0)
        assert viewer.connected
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)


def test_plain_viewer_against_tls_host_fails(tmp_path):
    """A non-TLS viewer cannot finish the handshake against a TLS host."""
    host, _, _ = _start_tls_host(tmp_path)
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
        )
        with pytest.raises((OSError, AuthenticationError)):
            viewer.connect(timeout=2.0)
        # Host should refuse to count an incomplete handshake as connected.
        assert _wait_until(lambda: host.connected_clients == 0, timeout=2.0)
    finally:
        host.stop(timeout=1.0)


def test_tls_client_against_plain_host_fails():
    """A TLS-only viewer cannot speak to a plain TCP host."""
    host = RemoteDesktopHost(
        token="tok", bind="127.0.0.1", port=0, fps=50.0,
        frame_provider=lambda: b"plain",
        input_dispatcher=lambda *_a, **_k: None,
        host_id="222222222",
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            ssl_context=_insecure_client_context(),
        )
        with pytest.raises((OSError, ssl.SSLError, AuthenticationError)):
            viewer.connect(timeout=2.0)
    finally:
        host.stop(timeout=1.0)


def test_tls_uses_socket_class_after_wrap(tmp_path):
    """After connect, the viewer's socket should be an SSLSocket."""
    host, cert_path, _ = _start_tls_host(tmp_path)
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="tok",
            ssl_context=_trusting_client_context(cert_path),
        )
        viewer.connect(timeout=2.0)
        assert isinstance(viewer._sock, ssl.SSLSocket)  # noqa: SLF001
        viewer.disconnect()
    finally:
        host.stop(timeout=1.0)
