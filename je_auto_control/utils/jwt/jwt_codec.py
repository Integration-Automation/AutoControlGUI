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
import math
import re
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


_B64URL_SEGMENT = re.compile(r"[A-Za-z0-9_-]*")


def _b64url_decode(segment: str) -> bytes:
    # urlsafe_b64decode drops characters outside the alphabet, so "sig!!"
    # verified like "sig": many token strings per signature, which defeats a
    # denylist or replay cache keyed on the token.
    if not _B64URL_SEGMENT.fullmatch(segment):
        raise JwtError("malformed base64url segment")
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(segment + padding)
    except (ValueError, TypeError) as exc:
        raise JwtError("malformed base64url segment") from exc
    # The last character's unused low bits are ignored by the decoder, so a
    # segment is only accepted in its one canonical spelling.
    if _b64url_encode(raw) != segment:
        raise JwtError("non-canonical base64url segment")
    return raw


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
    header = {"typ": "JWT"}
    if headers:
        header.update(headers)
    # Set last: an "alg" in ``headers`` labelled an HS256 token "none" (or
    # HS512, which then could not be decoded).
    header["alg"] = alg
    header_segment = _b64url_encode(json.dumps(
        header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(
        dict(claims), separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = _b64url_encode(_sign(signing_input, key, alg))
    return f"{header_segment}.{payload_segment}.{signature}"


def _json_object(segment: str, what: str) -> Dict[str, Any]:
    """Decode a JSON-object segment; anything else is a :class:`JwtError`."""
    try:
        value = json.loads(_b64url_decode(segment))
    except (ValueError, RecursionError) as exc:  # JSONDecodeError, UnicodeDecodeError, deep nesting
        raise JwtError(f"{what} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise JwtError(f"{what} must be a JSON object")
    return value


def _split_token(token: str) -> tuple:
    if not isinstance(token, str):
        raise JwtError("token must be a string")
    parts = token.split(".")
    if len(parts) != 3:
        raise JwtError("token must have three segments")
    # Checked up front: the signing input is encoded as ASCII before the
    # signature segment is ever decoded.
    if not all(_B64URL_SEGMENT.fullmatch(part) for part in parts):
        raise JwtError("malformed base64url segment")
    return parts[0], parts[1], parts[2]


def _verify_signature(header_seg: str, payload_seg: str, signature_seg: str,
                      key: Key, algorithms: Iterable[str]) -> Dict[str, Any]:
    header = _json_object(header_seg, "header")
    alg = header.get("alg")
    # A list or object "alg" is unhashable: the membership test raised a bare
    # TypeError that escaped every ``except JwtError``.
    if not isinstance(alg, str) or alg == "none" or alg not in _ALGORITHMS:
        raise JwtError(f"algorithm {alg!r} is not allowed")
    # RFC 7515 4.1.11: a token naming critical extensions must be rejected
    # unless every one is understood, and none are.
    if "crit" in header:
        raise JwtError(f"unsupported critical header parameters: {header['crit']!r}")
    if alg not in set(algorithms):
        raise JwtError(f"algorithm {alg!r} is not in the allowed set")
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected = _sign(signing_input, key, alg)
    if not hmac.compare_digest(expected, _b64url_decode(signature_seg)):
        raise InvalidSignatureError("signature verification failed")
    return header


def _numeric_claim(claims: Mapping[str, Any], name: str) -> float:
    """A time claim as a finite number.

    ``exp: "soon"`` raised a bare ``ValueError``, and ``exp: NaN`` (valid in
    Python's JSON) compared false with every time, so the token never expired.
    """
    value = claims[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JwtError(f"{name} claim must be a finite number")
    try:
        number = float(value)   # an int past float range raises OverflowError
    except OverflowError as exc:
        raise JwtError(f"{name} claim must be a finite number") from exc
    if not math.isfinite(number):
        raise JwtError(f"{name} claim must be a finite number")
    return number


def _check_time_claims(claims: Mapping[str, Any], now: float,
                       policy: "ClaimsPolicy") -> None:
    if policy.verify_exp and "exp" in claims and \
            now >= _numeric_claim(claims, "exp") + policy.leeway:
        # RFC 7519 4.1.4: not accepted "on or after" the expiration time.
        raise ExpiredTokenError("token has expired")
    if policy.verify_nbf and "nbf" in claims and \
            now < _numeric_claim(claims, "nbf") - policy.leeway:
        raise JwtError("token is not yet valid (nbf)")


def _check_audience(claims: Mapping[str, Any], audience: Any) -> None:
    if audience is None:
        return
    allowed = {audience} if isinstance(audience, str) else set(audience)
    actual = claims.get("aud")
    if isinstance(actual, str):
        actual_set = {actual}
    elif actual is None:
        actual_set = set()
    elif isinstance(actual, list) and all(isinstance(item, str) for item in actual):
        actual_set = set(actual)
    else:
        # aud: 5 raised TypeError from set().
        raise JwtError("audience claim must be a string or a list of strings")
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
    claims = _json_object(payload_seg, "payload")
    when = time.time() if now is None else now
    _check_time_claims(claims, when, policy)
    _check_audience(claims, policy.audience)
    if policy.issuer is not None and claims.get("iss") != policy.issuer:
        raise JwtError("issuer claim mismatch")
    return claims
