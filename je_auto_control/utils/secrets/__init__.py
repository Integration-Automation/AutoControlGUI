"""Encrypted secret store for action scripts.

Action JSON references secrets through ``${secrets.NAME}`` placeholders;
the runtime interpolator queries :data:`default_secret_manager` when it
sees that prefix. The manager keeps a per-vault salt and stores Fernet
tokens on disk — secrets are never written in plaintext.
"""
from je_auto_control.utils.secrets.secret_store import (
    SecretManager, SecretStoreError, SecretStoreLocked,
    default_secret_manager, default_secret_store_path,
)

__all__ = [
    "SecretManager", "SecretStoreError", "SecretStoreLocked",
    "default_secret_manager", "default_secret_store_path",
]
