"""Key material + CSR helpers for the TLS automation flow."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID as _NameOID


_DEFAULT_KEY_BITS = 2048


@dataclass
class KeyMaterial:
    """A private key + its on-disk paths."""
    private_key: rsa.RSAPrivateKey
    key_path: Optional[Path] = None

    def to_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def save_pem(self, path) -> Path:
        target = Path(os.path.expanduser(str(path)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.to_pem())
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        self.key_path = target
        return target


def _generate_key(bits: int = _DEFAULT_KEY_BITS) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(
        public_exponent=65537, key_size=int(bits),
    )


def generate_account_key(*, save_to: Optional[str] = None,
                         bits: int = _DEFAULT_KEY_BITS) -> KeyMaterial:
    """Create a new ACME account key (RSA-2048 by default)."""
    material = KeyMaterial(private_key=_generate_key(bits))
    if save_to:
        material.save_pem(save_to)
    return material


def generate_certificate_key(*, save_to: Optional[str] = None,
                             bits: int = _DEFAULT_KEY_BITS,
                             ) -> KeyMaterial:
    """Create a per-domain certificate key.

    Kept as a separate function so a caller can rotate the cert key
    independently of the ACME account key on each renewal.
    """
    return generate_account_key(save_to=save_to, bits=bits)


def generate_csr(key: rsa.RSAPrivateKey, *,
                 common_name: str,
                 san: Optional[Sequence[str]] = None) -> bytes:
    """Build a CSR (PEM) for the given common name and SAN list."""
    if not common_name:
        raise ValueError("common_name is required")
    subject = x509.Name([
        x509.NameAttribute(_NameOID.COMMON_NAME, common_name),
    ])
    sans = list(san or [])
    if common_name not in sans:
        sans.insert(0, common_name)
    builder = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(host) for host in sans],
            ),
            critical=False,
        )
    )
    csr = builder.sign(key, hashes.SHA256())
    return csr.public_bytes(serialization.Encoding.PEM)


def parse_certificate_expiry(pem_bytes: bytes) -> datetime:
    """Return the ``not_after`` timestamp from a PEM certificate."""
    if not pem_bytes:
        raise ValueError("certificate bytes empty")
    cert = x509.load_pem_x509_certificate(pem_bytes)
    # Prefer the timezone-aware accessor when available (cryptography
    # >= 42), fall back to the legacy naive ``not_valid_after``.
    not_after = getattr(cert, "not_valid_after_utc", None)
    if not_after is None:
        not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
    return not_after


__all__ = [
    "KeyMaterial", "generate_account_key", "generate_certificate_key",
    "generate_csr", "parse_certificate_expiry",
]
