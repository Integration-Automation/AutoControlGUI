"""One-time-password (TOTP) generation for automated 2FA logins."""
from je_auto_control.utils.otp.otp import (
    TOTPError, generate_secret, generate_totp, verify_totp,
)

__all__ = ["TOTPError", "generate_secret", "generate_totp", "verify_totp"]
