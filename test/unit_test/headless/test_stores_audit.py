"""User-store and secret-vault defects from the 2026-09-24 audit (fake values only).

A damaged ``users.json`` read as empty and the next save replaced every
user; ``"tags": 5`` raised a raw ``TypeError``; two users could share a
token. Two ``SecretManager``s on one vault overwrote each other's changes,
and a malformed vault raised ``KeyError`` / ``ValueError``.
"""
import json

import pytest

pytest.importorskip("cryptography")

from je_auto_control.utils.rbac.users import Role, UserAuthError, UserStore  # noqa: E402
from je_auto_control.utils.secrets.secret_store import (  # noqa: E402
    SecretManager, SecretStoreError, SecretStoreLocked,
)

PASS = "test-passphrase-1"


def test_a_damaged_user_file_is_not_overwritten(tmp_path):
    path = tmp_path / "users.json"
    store = UserStore(path)
    store.add_user(user_id="alice", display_name="Alice", role=Role.ADMIN)
    store.add_user(user_id="bob", display_name="Bob", role=Role.VIEWER)
    damaged = path.read_text(encoding="utf-8")[:-3]
    path.write_text(damaged, encoding="utf-8")
    reopened = UserStore(path)
    with pytest.raises(UserAuthError, match="unreadable"):
        reopened.add_user(user_id="carol", display_name="Carol", role=Role.VIEWER)
    assert path.read_text(encoding="utf-8") == damaged


def test_bad_tags_in_the_file_do_not_break_loading(tmp_path):
    path = tmp_path / "users.json"
    path.write_text(json.dumps({"users": [
        {"user_id": "a", "role": Role.VIEWER, "token_hash": "x", "tags": 5}]}), encoding="utf-8")
    assert UserStore(path).get("a").tags == []


def test_a_token_cannot_be_shared(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.add_user(user_id="admin1", display_name="A", role=Role.ADMIN, token="test-token-1")
    with pytest.raises(UserAuthError, match="in use"):
        store.add_user(user_id="viewer1", display_name="V", role=Role.VIEWER, token="test-token-1")
    assert store.authenticate("test-token-1").user_id == "admin1"


def test_two_managers_on_one_vault_keep_each_others_changes(tmp_path):
    path = tmp_path / "vault.json"
    first, second = SecretManager(path), SecretManager(path)
    first.initialize(PASS)
    assert second.unlock(PASS)
    first.set("A", "value-a")
    second.set("B", "value-b")
    assert first.list_names() == ["A", "B"]
    second.remove("A")
    assert first.get("A") is None


def test_a_vault_rekeyed_elsewhere_locks_this_manager(tmp_path):
    path = tmp_path / "vault.json"
    first, second = SecretManager(path), SecretManager(path)
    first.initialize(PASS)
    assert second.unlock(PASS)
    first.change_passphrase(PASS, "test-passphrase-2")
    with pytest.raises(SecretStoreLocked):
        second.set("A", "value-a")


@pytest.mark.parametrize("change", [
    lambda vault: vault.pop("salt"),
    lambda vault: vault.update(iterations=0),
    lambda vault: vault.update(salt="not base64!"),
    lambda vault: vault.update(items=[]),
])
def test_a_malformed_vault_is_a_store_error(tmp_path, change):
    path = tmp_path / "vault.json"
    SecretManager(path).initialize(PASS)
    vault = json.loads(path.read_text(encoding="utf-8"))
    change(vault)
    path.write_text(json.dumps(vault), encoding="utf-8")
    with pytest.raises(SecretStoreError):
        SecretManager(path).unlock(PASS)
