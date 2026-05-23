"""Phase 4.1: RFC 6238 TOTP (no external dependency).

The remote-desktop token is HMAC-protected but reusable — a leaked
token grants permanent access. TOTP layers a 6-digit OTP that rotates
every 30 s on top, so a stolen token alone is no longer enough.

Implementation notes:

* Pure stdlib (``hmac`` + ``hashlib`` + ``base64`` + ``secrets``) —
  zero new dependencies on top of CPython.
* SHA-1 by default to match Google Authenticator / Authy / 1Password.
* Verification accepts ±``window`` time steps so a viewer that is one
  step out of phase with the host (clock drift, network latency) can
  still authenticate.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse
from typing import Optional

_DEFAULT_DIGITS = 6
_DEFAULT_STEP = 30
_DEFAULT_WINDOW = 1
_SECRET_BYTES = 20  # RFC 4226 recommended size for HOTP/TOTP seeds.


class TOTPError(ValueError):
    """Raised for malformed secrets or codes."""


def generate_secret(num_bytes: int = _SECRET_BYTES) -> str:
    """Return a fresh base32 secret suitable for a TOTP authenticator app."""
    raw = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    """Tolerate user-typed secrets: strip spaces, pad, validate."""
    cleaned = "".join(secret.split()).upper()
    if not cleaned:
        raise TOTPError("secret must be non-empty")
    # base32 inputs need length to be a multiple of 8.
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    try:
        return base64.b32decode(cleaned + padding, casefold=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise TOTPError(f"invalid base32 secret: {exc}") from exc


def _code_for_counter(secret: bytes, counter: int,
                      digits: int = _DEFAULT_DIGITS,
                      digest: str = "sha1") -> str:
    counter_bytes = counter.to_bytes(8, "big")
    mac = hmac.new(secret, counter_bytes, getattr(hashlib, digest)).digest()
    offset = mac[-1] & 0x0F
    code_int = (
        ((mac[offset] & 0x7F) << 24)
        | ((mac[offset + 1] & 0xFF) << 16)
        | ((mac[offset + 2] & 0xFF) << 8)
        | (mac[offset + 3] & 0xFF)
    )
    code = code_int % (10 ** digits)
    return f"{code:0{digits}d}"


def generate_code(secret: str, *, at: Optional[float] = None,
                  step: int = _DEFAULT_STEP,
                  digits: int = _DEFAULT_DIGITS) -> str:
    """Return the current TOTP for ``secret``. Pass ``at`` to spoof time."""
    now = time.time() if at is None else at
    counter = int(now) // step
    return _code_for_counter(_decode_secret(secret), counter, digits=digits)


def verify_code(secret: str, code: str, *,
                at: Optional[float] = None,
                step: int = _DEFAULT_STEP,
                digits: int = _DEFAULT_DIGITS,
                window: int = _DEFAULT_WINDOW) -> bool:
    """Constant-time check of ``code`` against ``secret`` within ±``window`` steps."""
    if not isinstance(code, str):
        return False
    cleaned = code.strip()
    if len(cleaned) != digits or not cleaned.isdigit():
        return False
    decoded = _decode_secret(secret)
    now = time.time() if at is None else at
    base_counter = int(now) // step
    for delta in range(-window, window + 1):
        expected = _code_for_counter(
            decoded, base_counter + delta, digits=digits,
        )
        if hmac.compare_digest(expected, cleaned):
            return True
    return False


def provisioning_uri(secret: str, *, account: str,
                     issuer: str = "AutoControl",
                     digits: int = _DEFAULT_DIGITS,
                     step: int = _DEFAULT_STEP) -> str:
    """Build an ``otpauth://`` URI ready to be encoded as a QR code.

    Format follows the de-facto standard used by Google Authenticator,
    so a host operator can scan ``provisioning_uri(...)`` to enrol
    their phone instead of typing the base32 secret manually.
    """
    label = urllib.parse.quote(f"{issuer}:{account}", safe="")
    params = {
        "secret": secret.replace(" ", "").upper(),
        "issuer": issuer,
        "digits": str(digits),
        "period": str(step),
        "algorithm": "SHA1",
    }
    query = urllib.parse.urlencode(params)
    return f"otpauth://totp/{label}?{query}"


__all__ = [
    "TOTPError", "generate_secret", "generate_code", "verify_code",
    "provisioning_uri",
]
