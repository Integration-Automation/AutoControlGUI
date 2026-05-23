"""Phase 6.2: AES-GCM encrypted variant of :class:`JpegSequenceRecorder`.

Plain JPEG sequence recordings are sitting on disk in the clear —
anyone with filesystem access can re-assemble the session. This
recorder writes each frame as ``frame_NNNNNN.jpg.enc`` (nonce + AES-256-
GCM ciphertext + tag) and signs the manifest with HMAC-SHA256 so a
tampered manifest is detectable. The session key is generated at
:meth:`start` and never written to disk in the clear — wrap it with a
passphrase via :func:`derive_key_from_passphrase` or use one of the
``wrap_*`` helpers to encrypt it asymmetrically.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from base64 import b64encode
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MANIFEST_FILENAME = "manifest.json"
_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # 96-bit GCM nonce
_SALT_BYTES = 16
_PBKDF2_ITERATIONS = 600_000
_HMAC_KEY_BYTES = 32


def generate_session_key() -> bytes:
    """Return a fresh random 256-bit AES key."""
    return secrets.token_bytes(_KEY_BYTES)


def derive_key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 KDF for wrapping a session key with a user passphrase."""
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError("passphrase must be a non-empty string")
    if not isinstance(salt, (bytes, bytearray)) or len(salt) != _SALT_BYTES:
        raise ValueError(f"salt must be exactly {_SALT_BYTES} bytes")
    return hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), bytes(salt),
        _PBKDF2_ITERATIONS, _KEY_BYTES,
    )


class EncryptedJpegSequenceRecorder:
    """Like :class:`JpegSequenceRecorder` but every frame is AES-GCM ciphertext.

    The manifest tracks the salt + per-frame nonce + ciphertext SHA-256
    so playback can detect any single-byte tamper. Manifest itself is
    HMAC-signed so a swap of the manifest also fails verification.
    """

    def __init__(self, output_dir: str,
                 *, session_key: Optional[bytes] = None,
                 file_prefix: str = "frame",
                 digits: int = 6) -> None:
        self._dir = Path(os.path.expanduser(output_dir))
        self._prefix = file_prefix
        self._digits = max(1, int(digits))
        self._lock = threading.Lock()
        self._entries: List[Dict[str, object]] = []
        self._counter = 0
        self._started = False
        self._stopped = False
        self._started_at: Optional[float] = None
        if session_key is not None:
            if not isinstance(session_key, (bytes, bytearray)) \
                    or len(session_key) != _KEY_BYTES:
                raise ValueError(f"session_key must be {_KEY_BYTES} bytes")
            self._session_key = bytes(session_key)
        else:
            self._session_key = generate_session_key()
        self._aesgcm = AESGCM(self._session_key)
        # Independent key for HMAC-signing the manifest.
        self._hmac_key = secrets.token_bytes(_HMAC_KEY_BYTES)
        self._salt = secrets.token_bytes(_SALT_BYTES)

    @property
    def output_dir(self) -> Path:
        return self._dir

    @property
    def manifest_path(self) -> Path:
        return self._dir / _MANIFEST_FILENAME

    @property
    def frame_count(self) -> int:
        with self._lock:
            return self._counter

    @property
    def session_key(self) -> bytes:
        """The raw AES key — caller wraps + stores out-of-band."""
        return self._session_key

    @property
    def hmac_key(self) -> bytes:
        """Manifest signing key — separate from the frame key."""
        return self._hmac_key

    def start(self) -> None:
        with self._lock:
            if self._started:
                raise RuntimeError("recorder already started")
            self._dir.mkdir(parents=True, exist_ok=True)
            self._entries = []
            self._counter = 0
            self._started = True
            self._stopped = False
            self._started_at = time.time()

    def record_frame(self, payload: bytes) -> None:
        if not isinstance(payload, (bytes, bytearray)):
            return
        with self._lock:
            if not self._started or self._stopped:
                return
            self._counter += 1
            filename = (
                f"{self._prefix}_{self._counter:0{self._digits}d}.jpg.enc"
            )
            nonce = secrets.token_bytes(_NONCE_BYTES)
            entries = self._entries
            counter = self._counter
        # Encrypt outside the lock so concurrent record_frame calls can
        # parallelise the CPU-bound AES path.
        ciphertext = self._aesgcm.encrypt(nonce, bytes(payload), None)
        target = self._dir / filename
        try:
            target.write_bytes(nonce + ciphertext)
        except OSError:
            with self._lock:
                if entries and self._counter == counter:
                    self._counter -= 1
            return
        entry = {
            "filename": filename,
            "timestamp": time.time(),
            "size": len(ciphertext),
            "nonce": b64encode(nonce).decode("ascii"),
            "sha256": hashlib.sha256(ciphertext).hexdigest(),
        }
        with self._lock:
            entries.append(entry)

    def stop(self) -> Path:
        with self._lock:
            if not self._started:
                raise RuntimeError("recorder was never started")
            if self._stopped:
                return self.manifest_path
            self._stopped = True
            manifest = {
                "encrypted": True,
                "algorithm": "AES-256-GCM",
                "started_at": self._started_at,
                "stopped_at": time.time(),
                "frame_count": self._counter,
                "salt": b64encode(self._salt).decode("ascii"),
                "entries": list(self._entries),
            }
        # Sign the manifest body so a tamper of timestamps or counts
        # invalidates verification. Signature is computed over the
        # canonical JSON of the manifest *without* the signature field.
        body = json.dumps(manifest, sort_keys=True).encode("utf-8")
        signature = hmac.new(self._hmac_key, body, hashlib.sha256).digest()
        manifest["signature_hmac_sha256"] = b64encode(signature).decode("ascii")
        try:
            self.manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            pass
        return self.manifest_path


def verify_manifest(manifest_path, hmac_key: bytes) -> bool:
    """Recompute the manifest signature and verify it in constant time."""
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    declared_b64 = raw.pop("signature_hmac_sha256", None)
    if not isinstance(declared_b64, str):
        return False
    from base64 import b64decode
    declared = b64decode(declared_b64)
    expected = hmac.new(
        hmac_key,
        json.dumps(raw, sort_keys=True).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(expected, declared)


def decrypt_frame(ciphertext_with_nonce: bytes,
                  session_key: bytes) -> bytes:
    """Decrypt one ``.jpg.enc`` file produced by the recorder."""
    if len(ciphertext_with_nonce) <= _NONCE_BYTES:
        raise ValueError("encrypted frame is too short")
    nonce = ciphertext_with_nonce[:_NONCE_BYTES]
    ciphertext = ciphertext_with_nonce[_NONCE_BYTES:]
    return AESGCM(session_key).decrypt(nonce, ciphertext, None)


__all__ = [
    "EncryptedJpegSequenceRecorder",
    "generate_session_key",
    "derive_key_from_passphrase",
    "verify_manifest",
    "decrypt_frame",
]
