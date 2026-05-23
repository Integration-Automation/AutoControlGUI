"""Phase 7.5: RBAC user store + capability check tests."""
import json

import pytest

from je_auto_control.utils.rbac import (
    Capability, Role, UserAuthError, UserStore, can, role_capabilities,
)


# --- capability matrix ----------------------------------------------

@pytest.mark.parametrize("role,capability,expected", [
    (Role.VIEWER, Capability.READ_SCREEN, True),
    (Role.VIEWER, Capability.DRIVE_INPUT, False),
    (Role.VIEWER, Capability.MANAGE_USERS, False),
    (Role.OPERATOR, Capability.READ_SCREEN, True),
    (Role.OPERATOR, Capability.DRIVE_INPUT, True),
    (Role.OPERATOR, Capability.MANAGE_USERS, False),
    (Role.ADMIN, Capability.READ_SCREEN, True),
    (Role.ADMIN, Capability.MANAGE_USERS, True),
    (Role.ADMIN, Capability.READ_AUDIT, True),
])
def test_role_capability_matrix(role, capability, expected):
    assert can(role, capability) is expected


def test_role_capabilities_returns_set_copy():
    caps = role_capabilities(Role.ADMIN)
    caps.add("forge")  # should not affect the canonical set
    assert "forge" not in role_capabilities(Role.ADMIN)


def test_unknown_role_grants_nothing():
    assert role_capabilities("super_admin_god_mode") == set()


# --- UserStore ------------------------------------------------------

def test_add_and_authenticate_round_trip(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    plain = store.add_user(
        user_id="alice", display_name="Alice", role=Role.OPERATOR,
    )
    assert isinstance(plain, str) and len(plain) > 16
    record = store.authenticate(plain)
    assert record.user_id == "alice"
    assert record.role == Role.OPERATOR


def test_token_is_persisted_as_hash_not_plaintext(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    plain = store.add_user(
        user_id="alice", display_name="Alice", role=Role.VIEWER,
    )
    on_disk = json.loads((tmp_path / "users.json").read_text(encoding="utf-8"))
    [entry] = on_disk["users"]
    assert "token_hash" in entry
    assert plain not in json.dumps(on_disk)  # plain token nowhere on disk


def test_authenticate_constant_time_rejects_wrong_token(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    store.add_user(user_id="alice", display_name="Alice",
                   role=Role.VIEWER)
    with pytest.raises(UserAuthError, match="invalid"):
        store.authenticate("definitely-not-the-real-token")


def test_authenticate_rejects_empty_token(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    with pytest.raises(UserAuthError):
        store.authenticate("")


def test_duplicate_user_id_rejected(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    store.add_user(user_id="alice", display_name="A", role=Role.VIEWER)
    with pytest.raises(UserAuthError, match="already exists"):
        store.add_user(user_id="alice", display_name="A2", role=Role.ADMIN)


def test_add_user_rejects_unknown_role(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    with pytest.raises(UserAuthError, match="unknown role"):
        store.add_user(user_id="alice", display_name="A",
                       role="super_admin")


def test_remove_user_returns_true_only_for_existing(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    store.add_user(user_id="alice", display_name="A", role=Role.VIEWER)
    assert store.remove_user("alice") is True
    assert store.remove_user("alice") is False


def test_rotate_token_invalidates_old_token(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    first = store.add_user(user_id="alice", display_name="A",
                           role=Role.VIEWER)
    second = store.rotate_token("alice")
    assert first != second
    with pytest.raises(UserAuthError):
        store.authenticate(first)
    assert store.authenticate(second).user_id == "alice"


def test_set_role_changes_role_in_place(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    token = store.add_user(user_id="alice", display_name="A",
                           role=Role.VIEWER)
    store.set_role("alice", Role.ADMIN)
    record = store.authenticate(token)
    assert record.role == Role.ADMIN


def test_set_role_rejects_unknown(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    store.add_user(user_id="alice", display_name="A", role=Role.VIEWER)
    with pytest.raises(UserAuthError):
        store.set_role("alice", "super_admin")


def test_store_loads_from_disk(tmp_path):
    path = tmp_path / "users.json"
    first = UserStore(path=path)
    token = first.add_user(user_id="alice", display_name="A",
                           role=Role.OPERATOR)
    # Fresh instance should rediscover alice from the JSON file.
    second = UserStore(path=path)
    record = second.authenticate(token)
    assert record.user_id == "alice" and record.role == Role.OPERATOR


def test_explicit_token_is_accepted(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    stored_plain = store.add_user(
        user_id="alice", display_name="A", role=Role.VIEWER,
        token="my-secret-token-1234567890",
    )
    assert stored_plain == "my-secret-token-1234567890"
    record = store.authenticate("my-secret-token-1234567890")
    assert record.user_id == "alice"


def test_list_users_returns_snapshot(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    store.add_user(user_id="alice", display_name="A", role=Role.VIEWER)
    store.add_user(user_id="bob", display_name="B", role=Role.ADMIN)
    listing = store.list_users()
    assert {u.user_id for u in listing} == {"alice", "bob"}


def test_get_returns_none_for_unknown_user(tmp_path):
    store = UserStore(path=tmp_path / "users.json")
    assert store.get("ghost") is None
