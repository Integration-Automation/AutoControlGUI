"""Role-based access control: users, roles and token authentication.

The REST API and MCP server today accept a single shared bearer token —
fine for solo use but useless for a small team where one person should
only run read-only queries while another is allowed to drive the
mouse. This module adds:

  * A ``UserStore`` of user records (``id``, ``display_name``,
    ``role``, ``token_hash``) persisted as JSON.
  * Three baked-in roles (``viewer`` / ``operator`` / ``admin``) with
    a coarse-grained capability check (``can(role, capability)``).
  * Token authentication: ``authenticate(token)`` constant-time
    compares against every user's hashed token.

It is opt-in. The REST API and the MCP HTTP transport consult a store only
when one is configured -- ``JE_AUTOCONTROL_RBAC_USERS`` naming the file, or
a ``user_store=`` argument -- and otherwise keep their single shared token
exactly as before. With a store, each request is authenticated as one user
(:mod:`.authorization`), every REST route, MCP tool and privileged ``AC_*``
command is checked against the capability it needs (:mod:`.policy`), and
the audit entries carry the ``user_id``.

Work registered by an authenticated user and run later -- a scheduler job, a
trigger, a hotkey, a webhook, a watchdog rule -- runs as that user, with the
role they hold when it fires (:mod:`.deferred`). Users are managed through
:mod:`.admin`: ``AC_user_*``, the ``ac_user_*`` MCP tools,
``je_auto_control users`` and the REST API tab, all gated by ``manage_users``.

The store is intentionally tiny — no LDAP, no OAuth, no row-level
permissions. Operators who need more should stand up a proper IdP in
front of the REST endpoint; this is the "good-enough-for-small-team"
baseline.
"""
from je_auto_control.utils.rbac.admin import (
    IssuedToken, add_user, list_users, management_store, remove_user,
    rotate_user_token, set_user_role,
)
from je_auto_control.utils.rbac.authorization import (
    USERS_ENV, AuthorizationContext, AuthorizationError, authorization_scope,
    current_authorization, resolve_token, user_store_from_env,
)
from je_auto_control.utils.rbac.deferred import (
    DeferredOwner, adopted_scope, capture_owner, owner_scope, resolve_owner,
)
from je_auto_control.utils.rbac.policy import (
    authorize_command, capability_for_command, capability_for_route,
    capability_for_tool, denied_command_in,
)
from je_auto_control.utils.rbac.users import (
    Capability, Role, UserAuthError, UserRecord, UserStore,
    can, default_user_store, role_capabilities,
)

__all__ = [
    "AuthorizationContext", "AuthorizationError", "Capability", "DeferredOwner",
    "IssuedToken", "Role", "USERS_ENV", "UserAuthError", "UserRecord", "UserStore",
    "add_user", "adopted_scope", "authorization_scope", "authorize_command", "can",
    "capability_for_command", "capability_for_route", "capability_for_tool",
    "capture_owner", "current_authorization", "default_user_store",
    "denied_command_in", "list_users", "management_store", "owner_scope",
    "remove_user", "resolve_owner", "resolve_token", "role_capabilities",
    "rotate_user_token", "set_user_role", "user_store_from_env",
]
