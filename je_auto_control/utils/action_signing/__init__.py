"""Action-file security: Ed25519 / HMAC-SHA256 signing + Fernet encryption."""
from je_auto_control.utils.action_signing.asymmetric import create_signing_keypair
from je_auto_control.utils.action_signing.cipher import (
    decrypt_action_file, encrypt_action_file,
)
from je_auto_control.utils.action_signing.config import (
    SigningConfig, action_signing_config,
)
from je_auto_control.utils.action_signing.signer import (
    VerifyResult, read_signed_action_bytes, require_signed_actions,
    sign_action_file, signing_required, verify_action_file,
)

__all__ = [
    "SigningConfig",
    "VerifyResult",
    "action_signing_config",
    "create_signing_keypair",
    "decrypt_action_file",
    "encrypt_action_file",
    "read_signed_action_bytes",
    "require_signed_actions",
    "sign_action_file",
    "signing_required",
    "verify_action_file",
]
