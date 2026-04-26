"""HMAC-SHA256 challenge/response helpers shared by host and viewer."""
import hmac
import os
from hashlib import sha256

NONCE_BYTES = 32


def make_nonce() -> bytes:
    """Return a fresh random nonce for the auth handshake."""
    return os.urandom(NONCE_BYTES)


def compute_response(token: str, nonce: bytes) -> bytes:
    """Return ``HMAC_SHA256(token, nonce)`` for the given token."""
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    if not isinstance(nonce, (bytes, bytearray)) or len(nonce) != NONCE_BYTES:
        raise ValueError(f"nonce must be {NONCE_BYTES} bytes")
    return hmac.new(token.encode("utf-8"), bytes(nonce), sha256).digest()


def verify_response(token: str, nonce: bytes, response: bytes) -> bool:
    """Constant-time check that ``response`` matches the expected HMAC."""
    expected = compute_response(token, nonce)
    if not isinstance(response, (bytes, bytearray)):
        return False
    return hmac.compare_digest(expected, bytes(response))
