"""cryptography's floor is 50, and a missing wheel is a typed error. No Qt.

``cryptography>=48.0.1`` still admitted GHSA-g6cj-pr64-35w5 (high; the PKCS#7
EnvelopedData decryption oracle, ``>=44.0.0, <50.0.0``). The floor is declared
twice -- ``pyproject.toml`` for the stable package, ``dev.toml`` for the dev
one -- and resolved once in ``uv.lock``; all three have to agree.

Raising it costs Intel Macs their prebuilt wheel (49.0.0 dropped
``macosx_10_9_universal2``), and Windows arm64 has had none since 46.0.3. What
those platforms get instead is an error that says so: every door onto
``cryptography`` raises :class:`CryptographyUnavailableError`, which is in the
framework family and carries the install command.
"""
import pathlib
import re
import sys
from typing import Callable, Tuple

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, CryptographyUnavailableError,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]
FLOOR = (50, 0, 0)
ARM64_MARKER = "sys_platform != 'win32' or platform_machine != 'ARM64'"


def _version(text: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


@pytest.mark.parametrize("manifest", ["pyproject.toml", "dev.toml"])
def test_crypto_floor_is_fifty(manifest: str) -> None:
    """Both manifests declare the floor, and keep the Windows arm64 marker."""
    text = (ROOT / manifest).read_text(encoding="utf-8")
    declared = re.findall(r'^\s*"cryptography>=([\d.]+);\s*([^"]+)"', text, re.M)
    assert len(declared) == 1, f"{manifest} must require cryptography exactly once"
    minimum, marker = declared[0]
    assert _version(minimum) >= FLOOR
    assert marker.strip() == ARM64_MARKER


def test_the_lock_resolves_at_or_above_the_floor() -> None:
    """uv.lock is what CI installs; a stale lock would keep an old version."""
    text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    locked = re.search(r'^name = "cryptography"\nversion = "([\d.]+)"', text, re.M)
    assert locked is not None, "uv.lock no longer pins cryptography"
    assert _version(locked.group(1)) >= FLOOR
    assert "specifier = \">=50.0.0\"" in text, "uv.lock was not regenerated for the new floor"


def _vault_door() -> Callable[[], object]:
    from je_auto_control.utils.secrets import secret_store
    return secret_store._fernet_types


def _cipher_door() -> Callable[[], object]:
    from je_auto_control.utils.action_signing import cipher
    return cipher._fernet_types


def _key_pair_door() -> Callable[[], object]:
    from je_auto_control.utils.action_signing import asymmetric
    return asymmetric._ed25519


@pytest.mark.parametrize("door,blocked", [
    (_vault_door, "cryptography.fernet"),
    (_cipher_door, "cryptography.fernet"),
    (_key_pair_door, "cryptography.exceptions"),
])
def test_missing_crypto_feature_is_typed(monkeypatch, door, blocked: str) -> None:
    """A containment boundary catching AutoControlException sees this failure."""
    accessor = door()
    monkeypatch.setitem(sys.modules, blocked, None)
    with pytest.raises(CryptographyUnavailableError) as caught:
        accessor()
    assert isinstance(caught.value, AutoControlException)
    assert isinstance(caught.value, RuntimeError), "existing callers catch RuntimeError"
    assert "pip install cryptography" in str(caught.value)
    assert isinstance(caught.value.__cause__, ImportError)
