"""Regression tests for the resilience / config-sync / ACME defects of the 2026-09-23 audit.

A half-open circuit breaker let every concurrent caller through as a trial.
Config sync trusted the shape of the server's reply and let a hang-up out as
``RemoteDisconnected``; the ACME client let an unreachable CA and a bad CSR out
as ``URLError`` / ``ValueError``; ``renewal_due`` raised on a naive ``now``.
"""
import datetime as dt
import socket
import threading

import pytest

from je_auto_control.utils.config_sync.client import ConfigBucket, ConfigSyncClient, ConfigSyncError
from je_auto_control.utils.resilience.resilience import CircuitBreaker, CircuitOpenError


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _tripped():
    clock = _Clock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=10, clock=clock)
    with pytest.raises(ZeroDivisionError):
        breaker.call(lambda: 1 / 0)
    clock.now = 11.0  # past the reset timeout: half-open
    return breaker


def test_half_open_admits_one_trial_at_a_time():
    breaker = _tripped()
    entered, release = threading.Event(), threading.Event()

    def slow_trial():
        entered.set()
        release.wait(2.0)
        return "ok"

    trial = threading.Thread(target=lambda: breaker.call(slow_trial))
    trial.start()
    assert entered.wait(2.0)
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "second caller")
    release.set()
    trial.join()
    assert breaker.state == "closed"


def test_a_failed_trial_reopens_the_circuit():
    breaker = _tripped()
    with pytest.raises(ZeroDivisionError):
        breaker.call(lambda: 1 / 0)
    assert breaker.state == "open"


@pytest.mark.parametrize("body", [
    {"user_id": "u", "sections": {"hotkeys": [1, 2]}},
    {"user_id": "u", "sections": {"hotkeys": {"h1": "not a dict"}}},
    {"user_id": "u", "revision": "abc"},
    {"user_id": "u", "sections": {"hotkeys": {"h1": {"last_modified": "yesterday"}}}},
    {"user_id": "u", "sections": {"hotkeys": {"h1": {"last_modified": float("inf")}}}},
], ids=["section-list", "entry-string", "revision", "stamp-text", "stamp-inf"])
def test_a_malformed_bucket_is_a_sync_error(body):
    with pytest.raises(ConfigSyncError):
        ConfigBucket.from_dict(body)


def test_a_server_that_hangs_up_is_a_sync_error():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def hang_up():
        connection, _ = listener.accept()
        connection.recv(4096)
        connection.close()
        listener.close()

    threading.Thread(target=hang_up, daemon=True).start()
    client = ConfigSyncClient(f"http://127.0.0.1:{listener.getsockname()[1]}", user_id="u")
    with pytest.raises(ConfigSyncError):
        client.fetch()


def test_an_unreachable_ca_is_an_acme_error():
    pytest.importorskip("cryptography")
    from je_auto_control.utils.acme_v2.client import AcmeClient, AcmeError
    from je_auto_control.utils.tls_acme.keys import _generate_key
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()  # nothing listens here now
    client = AcmeClient(directory_url=f"http://127.0.0.1:{port}/dir",
                        account_key=_generate_key(1024), timeout_s=2)
    with pytest.raises(AcmeError):
        client._http("GET", f"http://127.0.0.1:{port}/dir")


def test_a_bad_csr_is_a_jws_error():
    pytest.importorskip("cryptography")
    from je_auto_control.utils.acme_v2.jws import JwsError, csr_to_b64url
    with pytest.raises(JwsError):
        csr_to_b64url(b"-----BEGIN CERTIFICATE REQUEST-----\ngarbage\n-----END CERTIFICATE REQUEST-----\n")


def test_renewal_due_accepts_a_naive_now(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    from je_auto_control.utils.tls_acme.keys import _generate_key
    from je_auto_control.utils.tls_acme.renewal import renewal_due
    key = _generate_key(1024)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "t")])
    start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(start).not_valid_after(start + dt.timedelta(days=90))
            .sign(key, hashes.SHA256()))
    path = tmp_path / "cert.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    assert renewal_due(path, now=dt.datetime(2026, 1, 2)) is False
    assert renewal_due(path, now=dt.datetime(2026, 3, 20)) is True
