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

It is a building block only: the REST API and the MCP server do not consult
it yet, and the audit log has no ``user_id`` field -- both still use their
single shared token.

The store is intentionally tiny — no LDAP, no OAuth, no row-level
permissions. Operators who need more should stand up a proper IdP in
front of the REST endpoint; this is the "good-enough-for-small-team"
baseline.
"""
from je_auto_control.utils.rbac.users import (
    Capability, Role, UserAuthError, UserRecord, UserStore,
    can, default_user_store, role_capabilities,
)

__all__ = [
    "Capability", "Role", "UserAuthError", "UserRecord", "UserStore",
    "can", "default_user_store", "role_capabilities",
]
