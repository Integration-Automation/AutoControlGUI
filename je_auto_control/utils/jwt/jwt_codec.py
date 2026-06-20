"""Encode and decode JSON Web Tokens (HS256/384/512) with the standard library.

RPA flows constantly need to mint or verify bearer tokens for the APIs they
drive, but the framework only had HMAC *file* signing (``action_signing``) and
an ACME-bound RS256 JWS (``acme_v2``) — neither produces or validates a compact
bearer JWT. This adds a focused, pure-stdlib JWT codec: the HMAC family plus
full claim validation, designed to feed straight into ``http_request``'s bearer
auth.

Security: the decoder rejects ``alg: "none"`` and only accepts an algorithm the
caller explicitly allow-lists (defeating the classic algorithm-confusion /
downgrade attack), and compares signatures with ``hmac.compare_digest``. RSA/EC
algorithms (RS256/ES256) are intentionally out of scope — they need a
third-party crypto library.

Pure standard library (``hmac`` + ``hashlib`` + ``base64`` + ``json``); the
clock is injectable so ``exp`` / ``nbf`` checks are deterministic. Imports no
``PySide6``.
"""
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Union

from je_auto_control.utils.exception.exceptions import AutoControlException

_ALGORITHMS = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}

Key = Union[str, bytes]


class JwtError(AutoControlException):
    """Base error for JWT encoding / decoding failures."""


class ExpiredTokenError(JwtError):
    """The token's ``exp`` claim is in the past."""


class InvalidSignatureError(JwtError):
    """The token signature does not match."""


@dataclass(frozen=True)
class ClaimsPolicy:
    """Validation policy for :func:`decode_jwt` (groups the claim-check knobs)."""

    algorithms: Sequence[str] = ("HS256",)
    audience: Any = None
    issuer: Optional[str] = None
    leeway: float = 0.0
    verify_exp: bool = True
    verify_nbf: bool = True


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except (ValueError, TypeError) as exc:
        raise JwtError("malformed base64url segment") from exc


def _as_bytes(key: Key) -> bytes:
    return key.encode("utf-8") if isinstance(key, str) else key


def _sign(signing_input: bytes, key: Key, alg: str) -> bytes:
    digest = _ALGORITHMS.get(alg)
    if digest is None:
        raise JwtError(f"unsupported algorithm {alg!r}")
    return hmac.new(_as_bytes(key), signing_input, digest).digest()


def encode_jwt(claims: Mapping[str, Any], key: Key, *, alg: str = "HS256",
               headers: Optional[Mapping[str, Any]] = None) -> str:
    """Return a signed compact JWT for ``claims``."""
    if alg not in _ALGORITHMS:
        raise JwtError(f"unsupported algorithm {alg!r}")
    header = {"alg": alg, "typ": "JWT"}
    if headers:
        header.update(headers)
    header_segment = _b64url_encode(json.dumps(
        header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(
        dict(claims), separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = _b64url_encode(_sign(signing_input, key, alg))
    return f"{header_segment}.{payload_segment}.{signature}"


def _split_token(token: str) -> tuple:
    parts = token.split(".")
    if len(parts) != 3:
        raise JwtError("token must have three segments")
    return parts[0], parts[1], parts[2]


def _verify_signature(header_seg: str, payload_seg: str, signature_seg: str,
                      key: Key, algorithms: Iterable[str]) -> Dict[str, Any]:
    header = json.loads(_b64url_decode(header_seg))
    alg = header.get("alg")
    if alg == "none" or alg not in _ALGORITHMS:
        raise JwtError(f"algorithm {alg!r} is not allowed")
    if alg not in set(algorithms):
        raise JwtError(f"algorithm {alg!r} is not in the allowed set")
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected = _sign(signing_input, key, alg)
    if not hmac.compare_digest(expected, _b64url_decode(signature_seg)):
        raise InvalidSignatureError("signature verification failed")
    return header


def _check_time_claims(claims: Mapping[str, Any], now: float,
                       policy: "ClaimsPolicy") -> None:
    if policy.verify_exp and "exp" in claims and \
            now > float(claims["exp"]) + policy.leeway:
        raise ExpiredTokenError("token has expired")
    if policy.verify_nbf and "nbf" in claims and \
            now < float(claims["nbf"]) - policy.leeway:
        raise JwtError("token is not yet valid (nbf)")


def _check_audience(claims: Mapping[str, Any], audience: Any) -> None:
    if audience is None:
        return
    allowed = {audience} if isinstance(audience, str) else set(audience)
    actual = claims.get("aud")
    actual_set = {actual} if isinstance(actual, str) else set(actual or [])
    if allowed.isdisjoint(actual_set):
        raise JwtError("audience claim mismatch")


def decode_jwt(token: str, key: Key, policy: Optional[ClaimsPolicy] = None, *,
               now: Optional[float] = None) -> Dict[str, Any]:
    """Verify ``token`` against ``policy`` and return its claims.

    Raises a :class:`JwtError` subclass on any failure. ``policy`` defaults to
    HS256-only with ``exp``/``nbf`` verification and no audience/issuer check.
    """
    policy = policy or ClaimsPolicy()
    header_seg, payload_seg, signature_seg = _split_token(token)
    _verify_signature(header_seg, payload_seg, signature_seg, key,
                      policy.algorithms)
    claims = json.loads(_b64url_decode(payload_seg))
    when = time.time() if now is None else now
    _check_time_claims(claims, when, policy)
    _check_audience(claims, policy.audience)
    if policy.issuer is not None and claims.get("iss") != policy.issuer:
        raise JwtError("issuer claim mismatch")
    return claims
