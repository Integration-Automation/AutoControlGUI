"""Opt-in user roles shared by REST, MCP and local administration.

Set JE_AUTOCONTROL_USERS to a user-store JSON path for individual bearer
identities. Unconfigured servers retain shared-token authentication.
"""
from je_auto_control.utils.rbac.users import (
    Capability, Role, UserAuthError, UserRecord, UserStore,
    can, default_user_store, role_capabilities,
)
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, AuthorizationError, authorization_scope, configured_user_store,
)
from je_auto_control.utils.rbac.user_api import (
    rbac_add_user, rbac_list_users, rbac_remove_user, rbac_rotate_token, rbac_set_role,
)

__all__ = [
    "Capability", "Role", "UserAuthError", "UserRecord", "UserStore",
    "can", "default_user_store", "role_capabilities",
    "AuthorizationContext", "AuthorizationError", "authorization_scope", "configured_user_store",
    "rbac_add_user", "rbac_list_users", "rbac_remove_user", "rbac_rotate_token", "rbac_set_role",
]
