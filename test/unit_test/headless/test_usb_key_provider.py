"""Tests for the ACL HMAC key providers (DPAPI + vault-backed)."""
import platform

import pytest

from je_auto_control.utils.usb.passthrough import (
    AclRule, UsbAcl, VaultKeyProvider, dpapi_available,
    load_or_create_dpapi_key,
)
from je_auto_control.utils.usb.passthrough.key_provider import (
    dpapi_protect, dpapi_unprotect,
)

_IS_WINDOWS = platform.system() == "Windows"


# ---------------------------------------------------------------------------
# DPAPI (Windows-only)
# ---------------------------------------------------------------------------


def test_dpapi_available_matches_platform():
    assert dpapi_available() is _IS_WINDOWS


@pytest.mark.skipif(not _IS_WINDOWS, reason="DPAPI is Windows-only")
def test_dpapi_round_trip():
    secret = b"a-32-byte-key-or-anything-really"  # NOSONAR python:S6418 - test plaintext, not a real credential
    blob = dpapi_protect(secret)
    assert blob != secret  # actually encrypted
    assert dpapi_unprotect(blob) == secret


@pytest.mark.skipif(not _IS_WINDOWS, reason="DPAPI is Windows-only")
def test_load_or_create_dpapi_key_persists(tmp_path):
    path = tmp_path / "usb_acl.key.dpapi"
    key1 = load_or_create_dpapi_key(path)
    assert len(key1) == 32
    assert path.exists()
    # On-disk blob is encrypted, not the raw key.
    assert path.read_bytes() != key1
    # Second call returns the same key.
    assert load_or_create_dpapi_key(path) == key1


def test_load_or_create_dpapi_key_off_windows_raises():
    if _IS_WINDOWS:
        pytest.skip("Windows has DPAPI; negative path covered elsewhere")
    with pytest.raises(RuntimeError):
        load_or_create_dpapi_key("ignored.dpapi")


# ---------------------------------------------------------------------------
# Vault-backed key provider
# ---------------------------------------------------------------------------


class _FakeVault:
    """Minimal SecretManager stand-in (get/set string by name)."""

    def __init__(self):
        self._items = {}

    def get(self, name):
        return self._items.get(name)

    def set(self, name, value):
        self._items[name] = value


def test_vault_key_provider_creates_then_reuses():
    vault = _FakeVault()
    provider = VaultKeyProvider(vault)
    key1 = provider.get_or_create()
    assert len(key1) == 32
    # Stored as base64 text in the vault.
    assert vault.get("usb_acl_hmac")
    # Second provider over the same vault recovers the same key.
    key2 = VaultKeyProvider(vault).get_or_create()
    assert key1 == key2


def test_vault_key_gates_acl_signature(tmp_path):
    """A vault-derived key signs the ACL; a different key fails closed."""
    vault = _FakeVault()
    key = VaultKeyProvider(vault).get_or_create()
    path = tmp_path / "acl.json"
    acl = UsbAcl(path=path, hmac_key=key, default_policy="allow")
    acl.add_rule(AclRule(vendor_id="1050", product_id="0407", allow=True))
    # Same key → loads.
    assert UsbAcl(path=path, hmac_key=key).integrity_ok is True
    # Wrong key → fail closed.
    assert UsbAcl(path=path, hmac_key=b"\x09" * 32).integrity_ok is False
