"""JWS Flattened JSON serialization for ACME v2 (RFC 7515 + 8555).

ACME requires every authenticated request to be signed JWS, with the
public key either embedded (``jwk``, for new-account) or referenced
by URL (``kid``, for everything afterwards). We support **RS256**
which is what every Let's Encrypt account uses by default.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict, Mapping, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class JwsError(ValueError):
    """Raised when the JWS payload or key is malformed."""


def _b64url(raw: bytes) -> str:
    """RFC 7515 base64url: standard b64 with no padding and URL-safe chars."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _int_to_b64url(value: int) -> str:
    """Encode a positive integer as RFC 7518 base64url (big-endian, minimal)."""
    if value < 0:
        raise JwsError("integer must be non-negative")
    length = max(1, (value.bit_length() + 7) // 8)
    return _b64url(value.to_bytes(length, "big"))


def public_jwk(key: rsa.RSAPrivateKey) -> Dict[str, str]:
    """Return the public-key half of an RSA key as a JWK dict."""
    numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "e": _int_to_b64url(numbers.e),
        "n": _int_to_b64url(numbers.n),
    }


def build_jwk_thumbprint(key: rsa.RSAPrivateKey) -> str:
    """RFC 7638 JWK Thumbprint — base64url(sha256(canonical_jwk_json))."""
    jwk = public_jwk(key)
    # Canonical order: e, kty, n (alphabetical by key name).
    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]},
        separators=(",", ":"), sort_keys=False,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).digest()
    return _b64url(digest)


def key_authorization(token: str, key: rsa.RSAPrivateKey) -> str:
    """RFC 8555 §8.1: ``token + '.' + jwk_thumbprint``.

    Used as the body of the HTTP-01 challenge file at
    ``/.well-known/acme-challenge/<token>``.
    """
    if not isinstance(token, str) or not token:
        raise JwsError("token must be a non-empty string")
    return f"{token}.{build_jwk_thumbprint(key)}"


def sign_compact(*, key: rsa.RSAPrivateKey,
                 url: str, nonce: str,
                 payload: Optional[Mapping[str, Any]] = None,
                 kid: Optional[str] = None) -> Dict[str, str]:
    """Build a flattened-JSON JWS object ready to PUT/POST to an ACME endpoint.

    Pass ``kid`` for authenticated requests (any after new-account); pass
    no kid to use the embedded ``jwk`` form required by new-account itself.
    The payload may be ``None`` (which the ACME spec calls "POST-as-GET",
    e.g. fetching an authorization) or a JSON-serialisable mapping.
    """
    if not url or not nonce:
        raise JwsError("url and nonce are required")
    header: Dict[str, Any] = {"alg": "RS256", "nonce": nonce, "url": url}
    if kid is None:
        header["jwk"] = public_jwk(key)
    else:
        header["kid"] = kid
    protected_b64 = _b64url(
        json.dumps(header, separators=(",", ":")).encode("utf-8"),
    )
    if payload is None:
        payload_b64 = ""
    else:
        payload_b64 = _b64url(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )
    signing_input = f"{protected_b64}.{payload_b64}".encode("ascii")
    signature = key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return {
        "protected": protected_b64,
        "payload": payload_b64,
        "signature": _b64url(signature),
    }


def csr_to_b64url(csr_pem: bytes) -> str:
    """Strip the PEM armour and re-encode the DER body as base64url.

    ACME's ``finalize`` endpoint wants the CSR as a JWS payload field
    named ``csr`` whose value is base64url(DER).
    """
    if not csr_pem:
        raise JwsError("csr_pem is empty")
    # Defer to cryptography to parse the PEM, then re-emit as DER.
    from cryptography import x509
    csr = x509.load_pem_x509_csr(csr_pem)
    return _b64url(csr.public_bytes(serialization.Encoding.DER))


__all__ = [
    "JwsError", "build_jwk_thumbprint", "csr_to_b64url",
    "key_authorization", "public_jwk", "sign_compact",
]
