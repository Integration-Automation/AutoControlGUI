"""Work registered now and run later keeps the identity of whoever registered it.

A scheduler job, a trigger, a hotkey binding, a webhook, an e-mail trigger or
a watchdog rule fires on a daemon thread, long after the request that
registered it has been answered. The authorisation scope belongs to the
request's thread, so that later run had no caller at all: an operator could
register a job whose action file held ``AC_sign_action_file`` and the executor
would run it unchecked.

Each of those registries now stores a :class:`DeferredOwner` with the entry
(:func:`capture_owner`) and runs it inside :func:`owner_scope`. The role is
looked up again at that moment, not remembered: a user who was demoted loses
the privilege for work already registered, and work whose user was removed
does not run.

Registered outside any RBAC scope -- no user store configured, the GUI, a
script -- there is no owner and nothing changes.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional

from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, AuthorizationError, authorization_scope,
    current_authorization, user_store_from_env,
)
from je_auto_control.utils.rbac.users import Capability, UserStore


@dataclass(frozen=True)
class DeferredOwner:
    """The user a piece of deferred work runs as, and the role it had when registered."""

    user_id: str
    role: str
    #: Where the role is looked up when the work fires. Absent on an owner
    #: read back from a file; ``JE_AUTOCONTROL_RBAC_USERS`` is used then.
    store: Optional[UserStore] = field(default=None, compare=False, repr=False)

    def to_dict(self) -> Dict[str, str]:
        """The owner as plain JSON: the optional ``owner`` field of a saved entry."""
        return {"user_id": self.user_id, "role": self.role}

    @classmethod
    def from_dict(cls, value: Any) -> Optional["DeferredOwner"]:
        """The owner a saved entry names; ``None`` for an entry saved without one."""
        if not isinstance(value, dict):
            return None
        user_id, role = value.get("user_id"), value.get("role")
        if not isinstance(user_id, str) or not user_id or not isinstance(role, str):
            return None
        return cls(user_id=user_id, role=role)


def capture_owner() -> Optional[DeferredOwner]:
    """The current caller as an owner to store; ``None`` outside an RBAC scope."""
    caller = current_authorization()
    if caller is None:
        return None
    return DeferredOwner(user_id=caller.user_id, role=caller.role, store=caller.store)


def resolve_owner(owner: DeferredOwner) -> AuthorizationContext:
    """Who ``owner`` is right now, by the user store.

    Without any store to ask -- the owner came from a file and RBAC has since
    been switched off -- the role recorded at registration stands: it is the
    most the user was ever granted here.
    """
    store = owner.store if owner.store is not None else user_store_from_env()
    if store is None:
        return AuthorizationContext(user_id=owner.user_id, role=owner.role)
    store.refresh()
    record = store.get(owner.user_id)
    if record is None:
        raise AuthorizationError(
            f"user {owner.user_id!r}, who registered this work, is no longer in the user store")
    return AuthorizationContext(user_id=record.user_id, role=record.role, store=store)


@contextlib.contextmanager
def owner_scope(owner: Optional[DeferredOwner],
                capability: str = Capability.DRIVE_INPUT) -> Iterator[None]:
    """Run the enclosed deferred work as ``owner``, with the role it holds now.

    ``capability`` is what registering the work needed in the first place;
    an owner who no longer has it does not get the work run at all
    (:class:`AuthorizationError`). ``None`` -- work nobody owns -- leaves the
    thread as it is.
    """
    if owner is None:
        yield
        return
    caller = resolve_owner(owner)
    if not caller.allows(capability):
        raise AuthorizationError(
            f"deferred work of user {caller.user_id!r} needs the {capability!r} capability; "
            f"role {caller.role!r} no longer grants it", capability=capability)
    with authorization_scope(caller):
        yield


__all__ = ["DeferredOwner", "capture_owner", "owner_scope", "resolve_owner"]
