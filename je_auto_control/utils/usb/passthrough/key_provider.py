"""Pluggable HMAC-key sources for the USB ACL (open question 8 hardening).

:class:`UsbAcl` accepts ``hmac_key=<bytes>``; this module supplies that
key from a stronger store than the default plaintext ``.key`` file:

* :func:`load_or_create_dpapi_key` — Windows DPAPI. The key is encrypted
  at rest with ``CryptProtectData`` and bound to the current user +
  machine, so the on-disk blob is useless if copied elsewhere. No
  plaintext key ever touches disk. (Defense in depth; a same-user
  process can still call ``CryptUnprotectData``.)
* :class:`VaultKeyProvider` — stores the key inside the existing
  passphrase-encrypted secret vault. A same-user process *without* the
  passphrase cannot recover the key, which closes the residual risk the
  plaintext key file leaves open.

No new third-party dependency: DPAPI is reached through ``ctypes`` and
the vault reuses the project's :class:`SecretManager`.
"""
from __future__ import annotations

import base64
import platform
import secrets
from pathlib import Path
from typing import Optional

_KEY_BYTES = 32
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


def dpapi_available() -> bool:
    """True on Windows where ``crypt32`` can be loaded."""
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        ctypes.WinDLL("crypt32")  # type: ignore[attr-defined]  # reason: win32-only ctypes
        return True
    except OSError:
        return False


def _dpapi_call(func_name: str, data: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes as wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL(  # type: ignore[attr-defined]  # reason: win32-only ctypes
        "crypt32", use_last_error=True,
    )
    kernel32 = ctypes.WinDLL(  # type: ignore[attr-defined]  # reason: win32-only ctypes
        "kernel32", use_last_error=True,
    )
    func = getattr(crypt32, func_name)
    func.restype = wintypes.BOOL

    src_buf = ctypes.create_string_buffer(bytes(data), len(data))
    src = _Blob(len(data), ctypes.cast(src_buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    ok = func(
        ctypes.byref(src), None, None, None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    if not ok:
        last_error = ctypes.get_last_error()  # type: ignore[attr-defined]  # reason: win32-only ctypes
        raise RuntimeError(f"{func_name} failed: {last_error}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def dpapi_protect(data: bytes) -> bytes:
    """Encrypt ``data`` with the current user's DPAPI master key."""
    return _dpapi_call("CryptProtectData", data)


def dpapi_unprotect(blob: bytes) -> bytes:
    """Reverse :func:`dpapi_protect`."""
    return _dpapi_call("CryptUnprotectData", blob)


def load_or_create_dpapi_key(path: Path) -> bytes:
    """Return a 32-byte key, DPAPI-protected at ``path`` (Windows only)."""
    if not dpapi_available():
        raise RuntimeError("DPAPI is only available on Windows")
    target = Path(path)
    if target.exists():
        return dpapi_unprotect(target.read_bytes())
    key = secrets.token_bytes(_KEY_BYTES)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(dpapi_protect(key))
    return key


class VaultKeyProvider:
    """HMAC key stored inside the passphrase-encrypted secret vault.

    The vault must be unlocked (``manager.unlock(passphrase)``) before
    :meth:`get_or_create` is called. The key is held as base64 text under
    ``name`` in the vault, so it is only recoverable with the passphrase.
    """

    def __init__(self, manager: object, *, name: str = "usb_acl_hmac") -> None:
        self._manager = manager
        self._name = name

    def get_or_create(self) -> bytes:
        existing: Optional[str] = self._manager.get(self._name)  # type: ignore[attr-defined]
        if existing:
            return base64.b64decode(existing)
        key = secrets.token_bytes(_KEY_BYTES)
        self._manager.set(  # type: ignore[attr-defined]
            self._name, base64.b64encode(key).decode("ascii"),
        )
        return key


__all__ = [
    "VaultKeyProvider", "dpapi_available", "dpapi_protect",
    "dpapi_unprotect", "load_or_create_dpapi_key",
]
