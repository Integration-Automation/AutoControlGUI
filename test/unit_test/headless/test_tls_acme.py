"""Phase 7.6: tests for the TLS ACME helper layer."""
import socket
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from je_auto_control.utils.tls_acme import (
    HttpChallengeServer, KeyMaterial, RenewalScheduler,
    generate_account_key, generate_certificate_key,
    parse_certificate_expiry, renewal_due,
)
from je_auto_control.utils.tls_acme.keys import generate_csr


# --- key material ----------------------------------------------------

def test_generate_account_key_returns_rsa_key():
    material = generate_account_key()
    assert isinstance(material.private_key, rsa.RSAPrivateKey)
    assert material.private_key.key_size == 2048


def test_save_pem_writes_private_key_to_disk(tmp_path):
    target = tmp_path / "account.key"
    material = generate_account_key(save_to=str(target))
    assert target.exists()
    pem = target.read_bytes()
    assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    assert material.key_path == target


def test_generate_certificate_key_independent_of_account():
    account = generate_account_key()
    cert = generate_certificate_key()
    # Different objects, no sharing of the same private key.
    assert account.private_key is not cert.private_key


def test_generate_csr_includes_common_name_and_san():
    material = generate_account_key()
    csr_pem = generate_csr(
        material.private_key, common_name="host.example.com",
        san=["host.example.com", "alt.example.com"],
    )
    csr = x509.load_pem_x509_csr(csr_pem)
    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    assert cn_attrs[0].value == "host.example.com"
    san_ext = csr.extensions.get_extension_for_class(
        x509.SubjectAlternativeName,
    )
    names = {dns.value for dns in san_ext.value}
    assert names == {"host.example.com", "alt.example.com"}


def test_generate_csr_rejects_empty_common_name():
    material = generate_account_key()
    with pytest.raises(ValueError, match="common_name"):
        generate_csr(material.private_key, common_name="")


# --- HTTP-01 challenge server ----------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_http_challenge_server_serves_registered_token():
    server = HttpChallengeServer(host="127.0.0.1", port=_free_port())
    server.set_token("abc123", "abc123.keyAuthorization")
    server.start()
    try:
        url = (
            f"http://127.0.0.1:{server.port}"
            f"/.well-known/acme-challenge/abc123"
        )
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            body = resp.read().decode("utf-8")
        assert body == "abc123.keyAuthorization"
    finally:
        server.stop()


def test_http_challenge_server_404_for_unknown_token():
    server = HttpChallengeServer(host="127.0.0.1", port=_free_port())
    server.start()
    try:
        url = (
            f"http://127.0.0.1:{server.port}"
            f"/.well-known/acme-challenge/nope"
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=2.0)
        assert exc.value.code == 404
    finally:
        server.stop()


def test_http_challenge_server_404_for_unrelated_path():
    server = HttpChallengeServer(host="127.0.0.1", port=_free_port())
    server.start()
    try:
        url = f"http://127.0.0.1:{server.port}/index.html"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=2.0)
        assert exc.value.code == 404
    finally:
        server.stop()


def test_set_token_validates_arguments():
    server = HttpChallengeServer(host="127.0.0.1", port=_free_port())
    with pytest.raises(ValueError):
        server.set_token("", "auth")
    with pytest.raises(ValueError):
        server.set_token("token", "")


def test_start_is_idempotent_and_stop_is_idempotent():
    server = HttpChallengeServer(host="127.0.0.1", port=_free_port())
    server.start()
    server.start()  # second call must be a no-op
    server.stop()
    server.stop()  # second call must be a no-op
    assert server.is_running is False


# --- renewal scheduler -----------------------------------------------

def _write_cert(path: Path, not_after: datetime) -> None:
    """Write a self-signed cert with the given expiry to ``path``."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "test.local"),
    ])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_after - timedelta(days=90))
        .not_valid_after(not_after)
    )
    cert = builder.sign(private_key=key, algorithm=hashes.SHA256())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def test_renewal_due_for_missing_cert(tmp_path):
    assert renewal_due(tmp_path / "missing.pem") is True


def test_renewal_due_when_expiry_is_inside_threshold(tmp_path):
    cert = tmp_path / "cert.pem"
    soon = datetime.now(timezone.utc) + timedelta(days=5)
    _write_cert(cert, soon)
    assert renewal_due(cert, threshold=timedelta(days=30)) is True


def test_renewal_not_due_when_expiry_is_far(tmp_path):
    cert = tmp_path / "cert.pem"
    later = datetime.now(timezone.utc) + timedelta(days=60)
    _write_cert(cert, later)
    assert renewal_due(cert, threshold=timedelta(days=30)) is False


def test_parse_certificate_expiry_returns_aware_datetime(tmp_path):
    cert = tmp_path / "cert.pem"
    expiry = datetime.now(timezone.utc) + timedelta(days=10)
    _write_cert(cert, expiry)
    parsed = parse_certificate_expiry(cert.read_bytes())
    assert parsed.tzinfo is not None
    assert abs((parsed - expiry).total_seconds()) < 5


def test_renewal_scheduler_tick_runs_renew_when_due(tmp_path):
    cert = tmp_path / "cert.pem"  # doesn't exist → renewal due
    called = []

    def renew():
        called.append(True)
        _write_cert(cert, datetime.now(timezone.utc) + timedelta(days=90))

    scheduler = RenewalScheduler(
        cert, renew=renew, threshold=timedelta(days=30),
    )
    assert scheduler.tick() is True  # first tick should renew
    assert len(called) == 1
    # Second tick must NOT renew — the cert is now well outside threshold.
    assert scheduler.tick() is False


def test_renewal_scheduler_swallows_renew_errors_and_calls_on_failure(tmp_path):
    cert = tmp_path / "cert.pem"
    failures = []

    def boom():
        raise RuntimeError("ca down")

    scheduler = RenewalScheduler(
        cert, renew=boom, threshold=timedelta(days=30),
        on_failure=failures.append,
    )
    assert scheduler.tick() is True  # attempted; renew failed
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)


def test_scheduler_start_and_stop_are_idempotent(tmp_path):
    scheduler = RenewalScheduler(
        tmp_path / "cert.pem",
        renew=lambda: None,
        check_interval_s=10.0,
    )
    scheduler.start()
    scheduler.start()
    scheduler.stop()
    scheduler.stop()
    assert scheduler.is_running is False
