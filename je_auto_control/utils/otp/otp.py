"""Generate TOTP codes for automated 2FA logins.

2FA blocks unattended logins; teams bolt on pyotp/Twilio glue to mint a
code mid-flow. This exposes the TOTP engine that already backs
remote-desktop auth as a general flow utility: store the base32 secret
(ideally in the secrets store) and mint the current code to type into a
login form. Imports no ``PySide6``.
"""
from typing import Optional

from je_auto_control.utils.remote_desktop.totp import (
    TOTPError, generate_code, generate_secret, verify_code,
)

__all__ = ["TOTPError", "generate_secret", "generate_totp", "verify_totp"]


def generate_totp(secret: str, *, at: Optional[float] = None,
                  step: int = 30, digits: int = 6) -> str:
    """Return the current TOTP code for a base32 ``secret``.

    ``at`` spoofs the time (seconds since epoch) for deterministic tests.
    """
    return generate_code(secret, at=at, step=int(step), digits=int(digits))


def verify_totp(secret: str, code: str, *, at: Optional[float] = None,
                step: int = 30, digits: int = 6, window: int = 1) -> bool:
    """Return True if ``code`` is valid for ``secret`` (± ``window`` steps)."""
    return verify_code(secret, code, at=at, step=int(step),
                       digits=int(digits), window=int(window))
