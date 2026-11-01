"""Which signing keys this process was configured with, read at call time.

These environment variables separate the machine that signs from the machines
that execute:

``JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY``
    Path of the Ed25519 private key. Set it on the signing machine only.
``JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY``
    Path of the matching public key. Set it on every execution endpoint; an
    endpoint that has this and no private key verifies and cannot sign.
``JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE``
    Passphrase of the private key file, when it was created with one. Only
    the signing machine needs it; verifying uses the public key.
``JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES``
    Migration mode: also accept HMAC sidecars written before version 2.
    Anyone who can execute actions can produce one, so switch it off again
    once every file is signed with the key pair.

With none of them set, signing is the per-user HMAC it has always been.
This module is GUI-free and imports no Qt.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PRIVATE_KEY_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY"
PUBLIC_KEY_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY"
PASSPHRASE_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE"  # nosec B105  # reason: a variable's name
ACCEPT_LEGACY_ENV = "JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES"

_SWITCHED_ON = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class SigningConfig:
    """The signing keys one process holds, and whether it accepts HMAC sidecars."""

    private_key_path: Optional[Path]
    public_key_path: Optional[Path]
    accept_legacy: bool

    @property
    def asymmetric(self) -> bool:
        """Whether version-2 (Ed25519) signatures are configured at all."""
        return self.private_key_path is not None or self.public_key_path is not None

    @property
    def verify_only(self) -> bool:
        """Whether this process holds the public key and no private key."""
        return self.public_key_path is not None and self.private_key_path is None


def _path_from(name: str) -> Optional[Path]:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def signing_passphrase() -> Optional[bytes]:
    """The private key's passphrase from the environment, or ``None`` when unset.

    Kept out of :class:`SigningConfig`, whose ``repr`` ends up in logs.
    """
    value = os.environ.get(PASSPHRASE_ENV, "")
    return value.encode("utf-8") if value else None


def action_signing_config() -> SigningConfig:
    """Return the signing configuration the environment describes right now."""
    legacy = os.environ.get(ACCEPT_LEGACY_ENV, "").strip().lower() in _SWITCHED_ON
    return SigningConfig(
        private_key_path=_path_from(PRIVATE_KEY_ENV),
        public_key_path=_path_from(PUBLIC_KEY_ENV),
        accept_legacy=legacy,
    )
