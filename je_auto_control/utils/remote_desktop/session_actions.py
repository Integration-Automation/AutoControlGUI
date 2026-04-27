"""Headless helpers for remote-session UX: SAS injection, screen blanking.

Both functions are best-effort and platform-specific. Callers are expected
to handle ``RuntimeError`` for clear failure messaging in the GUI.
"""
from __future__ import annotations

import sys

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def send_secure_attention_sequence() -> None:
    """Inject Ctrl+Alt+Del on the host (Windows only).

    Requires the Windows policy ``SoftwareSASGeneration`` set to allow user
    services / apps to call ``SendSAS``. If it is set to "Services only"
    (the default), this raises ``RuntimeError`` even when the call returns
    success-looking — the SAS just no-ops silently. Document this in the
    UI so users know what to check.
    """
    if sys.platform != "win32":
        raise RuntimeError("Ctrl+Alt+Del injection is Windows-only")
    try:
        import ctypes
        sas_dll = ctypes.WinDLL("sas.dll")
    except (OSError, AttributeError) as error:
        raise RuntimeError(
            "sas.dll not available; SoftwareSASGeneration policy may be locked",
        ) from error
    try:
        # SendSAS(BOOL AsUser): TRUE = simulate as the current user, FALSE =
        # as a service. Calling from a regular GUI app, "as user" is correct.
        sas_dll.SendSAS(ctypes.c_int(1))
        autocontrol_logger.info("session_actions: SendSAS dispatched")
    except (OSError, AttributeError) as error:
        raise RuntimeError(f"SendSAS failed: {error}") from error


__all__ = ["send_secure_attention_sequence"]
