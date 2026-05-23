"""Encrypt credentials with the SecretManager, then read them back.

Secrets are stored in a Fernet-encrypted JSON vault at
``default_secret_store_path()`` (under your user-data dir). The
passphrase below is just a demo — in production, prompt for it at
startup or pull it from a platform keyring.

Requires:
    pip install cryptography
"""
import secrets
from pathlib import Path

import je_auto_control as ac


def main() -> None:
    # Use a throwaway path for this demo so it doesn't touch your real vault.
    vault_path = Path("./demo_vault.json")
    if vault_path.exists():
        vault_path.unlink()
    manager = ac.SecretManager(path=vault_path)

    # Demo-only passphrase. In production you would prompt for this or
    # pull it from a platform keyring — never hardcode a real one.
    passphrase = "correct horse battery staple"  # nosec B105  # NOSONAR python:S2068  # reason: example illustrating the API, throwaway vault
    manager.initialize(passphrase)
    print(f"created vault at {manager.path}")

    manager.set("github_token", f"ghp_{secrets.token_hex(20)}")
    manager.set("smtp_password", "very-strong-password")
    print(f"stored: {manager.list_names()}")

    # The Fernet key is cached in-memory after .unlock(); .lock() drops it.
    manager.lock()
    print("vault locked — secrets unreadable.")

    if not manager.unlock(passphrase):
        raise RuntimeError("unlock failed?!")
    print(f"unlocked again; github_token starts with "
          f"{manager.get('github_token')[:8]!r}")

    vault_path.unlink()  # cleanup demo file


if __name__ == "__main__":
    main()
