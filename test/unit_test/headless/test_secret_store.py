"""Tests for the encrypted secret vault and ${secrets.NAME} interpolation."""
from pathlib import Path

import pytest

# The vault depends on ``cryptography``; declared in pyproject.toml but skip
# cleanly when an older environment hasn't refreshed the lockfile yet.
pytest.importorskip("cryptography")

from je_auto_control.utils.script_vars.interpolate import interpolate_value  # noqa: E402
from je_auto_control.utils.secrets.secret_store import (  # noqa: E402
    SecretManager, SecretStoreError, SecretStoreLocked,
)


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "vault.json"


@pytest.fixture
def manager(vault_path: Path) -> SecretManager:
    return SecretManager(path=vault_path)


def test_initialize_creates_unlocked_vault(manager, vault_path):
    manager.initialize("hunter2")
    assert vault_path.exists()
    assert manager.is_unlocked
    assert manager.list_names() == []


def test_initialize_refuses_overwrite(manager):
    manager.initialize("first")
    manager.lock()
    with pytest.raises(SecretStoreError):
        manager.initialize("second")


def test_set_and_get_round_trips(manager):
    manager.initialize("pw")
    manager.set("api_token", "shhh")
    assert manager.get("api_token") == "shhh"


def test_locked_manager_rejects_reads(manager):
    manager.initialize("pw")
    manager.set("k", "v")
    manager.lock()
    with pytest.raises(SecretStoreLocked):
        manager.get("k")


def test_unlock_with_wrong_passphrase_returns_false(manager):
    manager.initialize("good")
    manager.lock()
    assert manager.unlock("bad") is False
    assert manager.unlock("good") is True


def test_unlock_persists_across_manager_instances(vault_path):
    first = SecretManager(path=vault_path)
    first.initialize("pw")
    first.set("name", "value")
    first.lock()

    second = SecretManager(path=vault_path)
    assert second.is_initialized
    assert second.unlock("pw") is True
    assert second.get("name") == "value"


def test_remove_returns_false_for_missing(manager):
    manager.initialize("pw")
    assert manager.remove("missing") is False
    manager.set("present", "x")
    assert manager.remove("present") is True
    assert manager.list_names() == []


def test_change_passphrase_re_encrypts_items(vault_path):
    mgr = SecretManager(path=vault_path)
    mgr.initialize("old")
    mgr.set("token", "abc")
    mgr.change_passphrase("old", "new")
    assert mgr.unlock("new") is True
    assert mgr.get("token") == "abc"


def test_secret_value_is_not_plaintext_on_disk(vault_path):
    mgr = SecretManager(path=vault_path)
    mgr.initialize("pw")
    mgr.set("token", "supersecret-12345")
    text = vault_path.read_text(encoding="utf-8")
    assert "supersecret-12345" not in text


def test_interpolate_uses_default_secret_manager(monkeypatch, tmp_path):
    from je_auto_control.utils import secrets as secrets_pkg
    fresh = SecretManager(path=tmp_path / "vault.json")
    monkeypatch.setattr(secrets_pkg, "default_secret_manager", fresh)
    fresh.initialize("pw")
    fresh.set("api_key", "tok-42")
    assert interpolate_value("${secrets.api_key}", {}) == "tok-42"
    assert interpolate_value("Bearer ${secrets.api_key}", {}) \
        == "Bearer tok-42"


def test_interpolate_locked_secret_raises(monkeypatch, tmp_path):
    from je_auto_control.utils import secrets as secrets_pkg
    fresh = SecretManager(path=tmp_path / "vault.json")
    monkeypatch.setattr(secrets_pkg, "default_secret_manager", fresh)
    fresh.initialize("pw")
    fresh.set("api_key", "tok")
    fresh.lock()
    with pytest.raises(ValueError, match="locked"):
        interpolate_value("${secrets.api_key}", {})


def test_interpolate_unknown_secret_raises(monkeypatch, tmp_path):
    from je_auto_control.utils import secrets as secrets_pkg
    fresh = SecretManager(path=tmp_path / "vault.json")
    monkeypatch.setattr(secrets_pkg, "default_secret_manager", fresh)
    fresh.initialize("pw")
    with pytest.raises(ValueError, match="Unknown secret"):
        interpolate_value("${secrets.missing}", {})
