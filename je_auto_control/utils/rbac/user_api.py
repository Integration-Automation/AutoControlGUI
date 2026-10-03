"""User-management command adapters; results contain metadata only."""
from typing import Dict

from je_auto_control.utils.rbac.authorization import configured_user_store, require_command
from je_auto_control.utils.rbac.users import UserAuthError, UserStore, default_user_store


def _store() -> UserStore:
    return configured_user_store() or default_user_store()


def _validate_token(token: str) -> None:
    if not isinstance(token, str) or not token:
        raise UserAuthError('a non-empty token must be supplied')


def _metadata(store: UserStore, user_id: str) -> Dict[str, object]:
    record = store.get(user_id)
    if record is None:
        raise UserAuthError(f"unknown user_id: {user_id!r}")
    return {"user_id": record.user_id, "display_name": record.display_name,
            "role": record.role, "tags": list(record.tags)}


def rbac_add_user(user_id: str, display_name: str, role: str, token: str) -> Dict[str, object]:
    """Add a user with an explicitly supplied token; never return the token."""
    require_command("AC_user_add")
    _validate_token(token)
    store = _store()
    store.add_user(user_id=user_id, display_name=display_name, role=role, token=token)
    return _metadata(store, user_id)


def rbac_list_users() -> Dict[str, object]:
    """List user metadata without authentication secrets or token hashes."""
    require_command("AC_user_list")
    store = _store()
    return {"users": [_metadata(store, record.user_id) for record in store.list_users()]}


def rbac_remove_user(user_id: str) -> Dict[str, object]:
    """Remove a user and report whether it existed."""
    require_command("AC_user_remove")
    return {"removed": _store().remove_user(user_id)}


def rbac_set_role(user_id: str, role: str) -> Dict[str, object]:
    """Change a user's role and return current metadata."""
    require_command("AC_user_set_role")
    store = _store()
    store.set_role(user_id, role)
    return _metadata(store, user_id)


def rbac_rotate_token(user_id: str, token: str) -> Dict[str, object]:
    """Replace a token without exposing it in command output or audit logs."""
    require_command("AC_user_rotate_token")
    _validate_token(token)
    store = _store()
    store.rotate_token(user_id, token=token)
    return _metadata(store, user_id)
