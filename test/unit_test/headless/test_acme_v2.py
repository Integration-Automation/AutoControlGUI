"""Phase 8.1: pure-Python ACME v2 client tests.

We don't hit a real ACME directory in the headless suite — that
would be flaky and slow. Instead the tests cover:

- JWS signing produces verifiable output (RS256 round-trip).
- key_authorization matches the RFC 8555 §8.1 format.
- The client correctly steps through the protocol with a stub HTTP
  layer that emulates a Let's Encrypt-shaped directory.
"""
import base64
import json
from typing import Any, Dict, List, Tuple

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from je_auto_control.utils.acme_v2 import (
    AcmeClient, AcmeError, build_jwk_thumbprint, key_authorization,
    sign_compact,
)
from je_auto_control.utils.acme_v2.jws import (
    JwsError, csr_to_b64url, public_jwk,
)
from je_auto_control.utils.tls_acme.keys import (
    generate_account_key, generate_certificate_key, generate_csr,
)


@pytest.fixture(scope="module")
def account_key():
    """One RSA key reused across the suite (key gen is expensive)."""
    return generate_account_key().private_key


# --- JWS / JWK ------------------------------------------------------

def test_public_jwk_has_rs256_fields(account_key):
    jwk = public_jwk(account_key)
    assert jwk["kty"] == "RSA"
    assert isinstance(jwk["e"], str) and len(jwk["e"]) > 0
    assert isinstance(jwk["n"], str) and len(jwk["n"]) > 100


def test_thumbprint_is_deterministic(account_key):
    a = build_jwk_thumbprint(account_key)
    b = build_jwk_thumbprint(account_key)
    assert a == b
    assert len(a) > 10  # base64url-encoded SHA-256


def test_key_authorization_format(account_key):
    auth = key_authorization("abc-token", account_key)
    token, _, thumbprint = auth.partition(".")
    assert token == "abc-token"
    assert thumbprint == build_jwk_thumbprint(account_key)


def test_key_authorization_rejects_empty_token(account_key):
    with pytest.raises(JwsError):
        key_authorization("", account_key)


def test_sign_compact_produces_verifiable_signature(account_key):
    jws = sign_compact(
        key=account_key, url="https://acme.example/new-order",
        nonce="nonce-1", payload={"x": 1},
    )
    assert {"protected", "payload", "signature"} <= jws.keys()
    protected = base64.urlsafe_b64decode(jws["protected"] + "==")
    header = json.loads(protected)
    assert header["alg"] == "RS256"
    assert header["nonce"] == "nonce-1"
    assert header["jwk"]["kty"] == "RSA"  # jwk form (no kid given)

    signing_input = f"{jws['protected']}.{jws['payload']}".encode("ascii")
    signature = base64.urlsafe_b64decode(jws["signature"] + "==")
    # Should NOT raise — the signature must verify against the public key.
    account_key.public_key().verify(
        signature, signing_input, padding.PKCS1v15(), hashes.SHA256(),
    )


def test_sign_compact_uses_kid_when_provided(account_key):
    jws = sign_compact(
        key=account_key, url="https://acme.example/order",
        nonce="n", payload=None, kid="https://acme.example/acct/42",
    )
    header = json.loads(
        base64.urlsafe_b64decode(jws["protected"] + "=="),
    )
    assert header["kid"] == "https://acme.example/acct/42"
    assert "jwk" not in header  # kid and jwk are mutually exclusive
    # POST-as-GET → payload field is the empty string per spec.
    assert jws["payload"] == ""


def test_sign_compact_requires_url_and_nonce(account_key):
    with pytest.raises(JwsError):
        sign_compact(key=account_key, url="", nonce="n", payload=None)
    with pytest.raises(JwsError):
        sign_compact(key=account_key, url="x", nonce="", payload=None)


def test_csr_to_b64url_round_trip(account_key):
    csr = generate_csr(account_key, common_name="host.example.com")
    encoded = csr_to_b64url(csr)
    assert isinstance(encoded, str) and len(encoded) > 50
    # All RFC 7515 base64url chars only.
    assert set(encoded) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
    )


def test_csr_to_b64url_rejects_empty():
    with pytest.raises(JwsError):
        csr_to_b64url(b"")


# --- AcmeClient driven by a stub HTTP layer ------------------------

class _StubServer:
    """Minimal scriptable ACME-like server for AcmeClient tests."""

    def __init__(self) -> None:
        self.nonce_counter = 0
        self.order_status = "ready"  # tests can mutate
        self.auth_status = "pending"
        self.issued_cert = b"-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n"
        # Captured payloads — for assertions in the tests.
        self.calls: List[Tuple[str, str]] = []

    def directory(self) -> Dict[str, Any]:
        return {
            "newNonce": "https://acme.example/new-nonce",
            "newAccount": "https://acme.example/new-acct",
            "newOrder": "https://acme.example/new-order",
        }

    def next_nonce(self) -> str:
        self.nonce_counter += 1
        return f"nonce-{self.nonce_counter}"


def _install_stub(monkeypatch, stub: _StubServer) -> List[Tuple]:
    """Patch AcmeClient._http to read from the stub."""
    recorded: List[Tuple] = []

    def fake_http(self, method, url, *, body=None,
                  content_type=None, accept=None):
        recorded.append((method, url))
        if method == "GET" and url.endswith("/directory"):
            return 200, stub.directory(), {}
        if method == "HEAD" and "/new-nonce" in url:
            return 200, b"", {"Replay-Nonce": stub.next_nonce()}
        # All other POSTs in this stub are JWS-signed; pretend we
        # accepted them and return a sensible body.
        headers = {"Replay-Nonce": stub.next_nonce()}
        if "/new-acct" in url:
            headers["Location"] = "https://acme.example/acct/1"
            return 201, {"status": "valid"}, headers
        if "/new-order" in url:
            headers["Location"] = "https://acme.example/order/1"
            return 201, {
                "status": stub.order_status,
                "authorizations": ["https://acme.example/authz/1"],
                "finalize": "https://acme.example/order/1/finalize",
                "identifiers": [{"type": "dns", "value": "example.com"}],
            }, headers
        if url.endswith("/authz/1"):
            return 200, {
                "status": stub.auth_status,
                "identifier": {"type": "dns", "value": "example.com"},
                "challenges": [{
                    "type": "http-01",
                    "url": "https://acme.example/chall/1",
                    "token": "tok-1",
                    "status": "pending",
                }],
            }, headers
        if url.endswith("/chall/1"):
            return 200, {"type": "http-01", "status": "pending"}, headers
        if url.endswith("/order/1/finalize"):
            return 200, {
                "status": "valid",
                "authorizations": ["https://acme.example/authz/1"],
                "finalize": "https://acme.example/order/1/finalize",
                "certificate": "https://acme.example/cert/1",
            }, headers
        if url.endswith("/order/1"):
            return 200, {
                "status": "valid",
                "authorizations": ["https://acme.example/authz/1"],
                "finalize": "https://acme.example/order/1/finalize",
                "certificate": "https://acme.example/cert/1",
            }, headers
        if url.endswith("/cert/1"):
            return 200, stub.issued_cert, headers
        return 404, b"", headers

    monkeypatch.setattr(AcmeClient, "_http", fake_http)
    return recorded


def test_full_request_certificate_flow(monkeypatch, account_key):
    stub = _StubServer()
    stub.auth_status = "valid"  # skip the polling wait
    _install_stub(monkeypatch, stub)

    cert_key = generate_certificate_key().private_key
    csr = generate_csr(cert_key, common_name="example.com")
    published: List[Tuple[str, str]] = []

    client = AcmeClient(
        directory_url="https://acme.example/directory",
        account_key=account_key,
    )
    cert_pem = client.request_certificate(
        domains=["example.com"], csr_pem=csr,
        http_publisher=lambda t, ka: published.append((t, ka)),
    )
    assert b"BEGIN CERTIFICATE" in cert_pem
    # The publisher should have been called with the matching key auth.
    assert len(published) == 1
    token, key_auth = published[0]
    assert token == "tok-1"
    assert key_auth.startswith("tok-1.")  # token + "." + thumbprint
    # kid must have been captured during new_account so subsequent
    # signed requests carry the kid form, not the jwk form.
    assert client._kid == "https://acme.example/acct/1"  # noqa: SLF001


def test_request_certificate_aborts_on_invalid_authorization(
        monkeypatch, account_key):
    stub = _StubServer()
    stub.auth_status = "invalid"
    _install_stub(monkeypatch, stub)

    csr = generate_csr(
        generate_certificate_key().private_key, common_name="example.com",
    )
    client = AcmeClient(
        directory_url="https://acme.example/directory",
        account_key=account_key,
    )
    with pytest.raises(AcmeError, match="invalid"):
        client.request_certificate(
            domains=["example.com"], csr_pem=csr,
            http_publisher=lambda _t, _k: None,
        )


def test_directory_cached_after_first_call(monkeypatch, account_key):
    stub = _StubServer()
    calls = _install_stub(monkeypatch, stub)
    client = AcmeClient(
        directory_url="https://acme.example/directory",
        account_key=account_key,
    )
    client.directory()
    client.directory()
    # Only one GET /directory — the second call is cached.
    directory_calls = [c for c in calls if c == ("GET", "https://acme.example/directory")]
    assert len(directory_calls) == 1


def test_new_order_requires_account_first(monkeypatch, account_key):
    stub = _StubServer()
    _install_stub(monkeypatch, stub)
    client = AcmeClient(
        directory_url="https://acme.example/directory",
        account_key=account_key,
    )
    with pytest.raises(AcmeError, match="new_account"):
        client.new_order(["example.com"])


def test_new_order_rejects_empty_domains(monkeypatch, account_key):
    stub = _StubServer()
    _install_stub(monkeypatch, stub)
    client = AcmeClient(
        directory_url="https://acme.example/directory",
        account_key=account_key,
    )
    client.new_account()
    with pytest.raises(AcmeError, match="domain"):
        client.new_order([])


def test_http_challenge_not_offered_raises(account_key):
    """AcmeAuthorization with no http-01 challenge raises a clear error."""
    from je_auto_control.utils.acme_v2.client import _build_authorization
    auth = _build_authorization(
        "https://acme.example/authz/1",
        {"status": "pending", "identifier": {"value": "example.com"},
         "challenges": [{"type": "dns-01", "url": "x", "token": "t",
                         "status": "pending"}]},
    )
    with pytest.raises(AcmeError, match="http-01"):
        auth.http_challenge()
