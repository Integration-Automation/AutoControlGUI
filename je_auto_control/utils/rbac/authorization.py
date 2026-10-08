"""Who is making this request: the authenticated user and the scope it runs in.

A server that has a :class:`~je_auto_control.utils.rbac.users.UserStore`
configured turns a bearer token into an :class:`AuthorizationContext` with
:func:`resolve_token` and serves the request inside
:func:`authorization_scope`. Code further down -- the executor, the MCP
dispatcher, the audit writers -- asks :func:`current_authorization` who the
caller is instead of having the identity threaded through every signature.

No scope means no RBAC: a deployment that never configured a user store, the
stdio MCP transport, a script calling the library directly. Nothing is
checked there, which is what keeps those callers working exactly as before.
"""
from __future__ import annotations

import contextlib
import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.users import UserAuthError, UserStore, can

#: Names the user store file. Setting it is what switches RBAC on for the
#: REST API and the MCP HTTP transport; unset or empty leaves both on their
#: shared token.
USERS_ENV = "JE_AUTOCONTROL_RBAC_USERS"


class AuthorizationError(AutoControlException, PermissionError):
    """The authenticated user's role does not grant what was asked for."""

    def __init__(self, message: str, capability: str = "") -> None:
        super().__init__(message)
        self.capability = capability


@dataclass(frozen=True)
class AuthorizationContext:
    """One authenticated caller: who it is and the role it holds."""

    user_id: str
    role: str

    def allows(self, capability: str) -> bool:
        """``True`` when this caller's role grants ``capability``."""
        return can(self.role, capability)


def user_store_from_env() -> Optional[UserStore]:
    """The user store ``JE_AUTOCONTROL_RBAC_USERS`` names, or ``None`` when unset.

    Only an explicit path opts in. The default ``~/.je_auto_control/users.json``
    is never picked up on its own: a file left there by an experiment must not
    silently retire the shared token of a running deployment.
    """
    raw = os.environ.get(USERS_ENV, "").strip()
    if not raw:
        return None
    return UserStore(Path(os.path.realpath(os.path.expanduser(raw))))


def resolve_token(store: UserStore, token: str) -> Optional[AuthorizationContext]:
    """The caller ``token`` belongs to, or ``None`` when it is nobody's.

    The store is re-read first when its file changed, so removing a user or
    rotating a token takes effect on the next request.
    """
    store.refresh()
    try:
        record = store.authenticate(token)
    except UserAuthError:
        return None
    return AuthorizationContext(user_id=record.user_id, role=record.role)


_CURRENT: ContextVar[Optional[AuthorizationContext]] = ContextVar(
    "je_auto_control_authorization", default=None)


def current_authorization() -> Optional[AuthorizationContext]:
    """The caller this thread is serving, or ``None`` outside any RBAC scope."""
    return _CURRENT.get()


@contextlib.contextmanager
def authorization_scope(context: Optional[AuthorizationContext]) -> Iterator[None]:
    """Serve the enclosed work as ``context``; ``None`` clears any outer scope.

    The scope belongs to the calling thread. Work handed to another thread --
    a scheduler job, a trigger, a hotkey -- runs outside it.
    """
    token = _CURRENT.set(context)
    try:
        yield
    finally:
        _CURRENT.reset(token)


__all__ = [
    "AuthorizationContext", "AuthorizationError", "USERS_ENV",
    "authorization_scope", "current_authorization", "resolve_token",
    "user_store_from_env",
]
