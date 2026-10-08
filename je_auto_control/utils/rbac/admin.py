"""Managing the users of a store: add, remove, change role, rotate token, list.

One implementation behind every surface -- the ``AC_user_*`` commands, the
``ac_user_*`` MCP tools, ``je_auto_control users ...`` and the GUI panel --
so the rules below hold whichever one is used:

* **Who may.** Inside an RBAC scope the caller needs ``manage_users`` (the
  admin role) and works on the store that authenticated them; naming another
  file is refused. Outside any scope -- the CLI bootstrapping the first admin,
  a script, the GUI of the desktop user -- nothing is checked, as with every
  other privileged call made directly on the host.
* **A store keeps an admin.** Removing or demoting the last admin is refused:
  afterwards nobody could manage users through any authenticated surface.
* **A token is shown once.** ``add`` and ``rotate`` return the plain token in
  an :class:`IssuedToken`, whose text form masks it, so the executor's result
  log and anything else that formats the result never holds it. Only the
  hash is stored, and the audit entry names the user, never the token.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rbac.authorization import (
    AuthorizationError, current_authorization, user_store_from_env,
)
from je_auto_control.utils.rbac.users import (
    Capability, Role, UserAuthError, UserRecord, UserStore,
)

_MASK = "<shown once>"


class IssuedToken(Dict[str, Any]):
    """The reply of ``add`` / ``rotate``: a plain dict whose text form hides ``token``.

    It serialises as JSON with the token in it -- that is the one time the
    caller sees it -- while ``str()`` / ``repr()``, which is what a log line
    or a formatted run record uses, show a placeholder.
    """

    def __repr__(self) -> str:
        return repr({key: _MASK if key == "token" else value for key, value in self.items()})

    __str__ = __repr__


def management_store(users_path: Optional[str] = None) -> UserStore:
    """The store a management call works on, after checking the caller may.

    An authenticated caller gets the store that identified them. Otherwise it
    is ``users_path``, else the file ``JE_AUTOCONTROL_RBAC_USERS`` names;
    with neither, :class:`UserAuthError` -- the default location is never
    assumed, for the reason :func:`user_store_from_env` gives.
    """
    caller = current_authorization()
    if caller is not None and not caller.allows(Capability.MANAGE_USERS):
        raise AuthorizationError(
            f"managing users needs the {Capability.MANAGE_USERS!r} capability; "
            f"user {caller.user_id!r} has role {caller.role!r}",
            capability=Capability.MANAGE_USERS)
    requested = _real(users_path) if users_path else None
    if caller is not None and caller.store is not None:
        if requested is not None and requested != _real(str(caller.store.path)):
            raise AuthorizationError(
                "an authenticated caller manages the user store that authenticated it; "
                "users_path may not name another file", capability=Capability.MANAGE_USERS)
        caller.store.refresh()  # another process may have changed the file
        return caller.store
    if requested is not None:
        return UserStore(requested)
    store = user_store_from_env()
    if store is None:
        raise UserAuthError(
            "no user store: pass users_path or set JE_AUTOCONTROL_RBAC_USERS")
    return store


def _real(path: str) -> Path:
    return Path(os.path.realpath(os.path.expanduser(path)))


def _public(record: UserRecord) -> Dict[str, Any]:
    """A user as it may be shown: everything but the token hash."""
    return {"user_id": record.user_id, "display_name": record.display_name,
            "role": record.role, "tags": list(record.tags)}


def _audit(event: str, user_id: str, detail: str) -> None:
    """Record a change to the user list; never the token, and never fatal."""
    caller = current_authorization()
    actor = caller.user_id if caller is not None else "local"
    autocontrol_logger.info("rbac %s user=%s by=%s %s", event, user_id, actor, detail)
    try:
        from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
        default_audit_log().log(
            f"rbac_{event}", viewer_id=actor, detail=f"user={user_id} {detail}".strip())
    except Exception as error:  # noqa: BLE001  # reason: the change is already saved; a failed audit write must not undo or hide it
        autocontrol_logger.warning("rbac %s not written to the audit log: %r", event, error)


def _admins(store: UserStore) -> List[str]:
    return [record.user_id for record in store.list_users() if record.role == Role.ADMIN]


def _keep_an_admin(store: UserStore, user_id: str, action: str) -> None:
    """Refuse ``action`` on ``user_id`` when it is the store's only admin."""
    if _admins(store) == [user_id]:
        raise UserAuthError(
            f"cannot {action} {user_id!r}: it is the only admin, and nobody could "
            "manage users afterwards; add another admin first")


def add_user(user_id: str, role: str = Role.VIEWER, display_name: str = "",
             tags: Optional[Sequence[str]] = None,
             users_path: Optional[str] = None) -> IssuedToken:
    """Add a user and return it with its token -- the only time the token is shown."""
    store = management_store(users_path)
    token = store.add_user(user_id=str(user_id), display_name=str(display_name or ""),
                           role=str(role), tags=list(tags) if tags else None)
    _audit("user_added", str(user_id), f"role={role}")
    record = store.get(str(user_id))
    shown = _public(record) if record is not None else {"user_id": str(user_id), "role": role}
    return IssuedToken({**shown, "token": token})


def remove_user(user_id: str, users_path: Optional[str] = None) -> Dict[str, Any]:
    """Remove a user; ``{"removed": False}`` when there was no such user."""
    store = management_store(users_path)
    _keep_an_admin(store, str(user_id), "remove")
    removed = store.remove_user(str(user_id))
    if removed:
        _audit("user_removed", str(user_id), "")
    return {"user_id": str(user_id), "removed": removed}


def set_user_role(user_id: str, role: str,
                  users_path: Optional[str] = None) -> Dict[str, Any]:
    """Change a user's role; it applies to their next request and their deferred work."""
    store = management_store(users_path)
    if role != Role.ADMIN:
        _keep_an_admin(store, str(user_id), "demote")
    store.set_role(str(user_id), str(role))
    _audit("user_role_set", str(user_id), f"role={role}")
    return {"user_id": str(user_id), "role": str(role)}


def rotate_user_token(user_id: str, users_path: Optional[str] = None) -> IssuedToken:
    """Replace a user's token and return the new one -- shown this once."""
    store = management_store(users_path)
    token = store.rotate_token(str(user_id))
    _audit("user_token_rotated", str(user_id), "")
    return IssuedToken({"user_id": str(user_id), "token": token})


def list_users(users_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every user as ``{user_id, display_name, role, tags}``; no token, no hash."""
    store = management_store(users_path)
    return [_public(record) for record in store.list_users()]


__all__ = [
    "IssuedToken", "add_user", "list_users", "management_store",
    "remove_user", "rotate_user_token", "set_user_role",
]
