"""Admin-only user management tools backed by the configured user store."""
from typing import List

from je_auto_control.utils.mcp_server.tools._base import (
    DESTRUCTIVE, MCPTool, NON_DESTRUCTIVE, READ_ONLY, schema,
)
from je_auto_control.utils.rbac.user_api import (
    rbac_add_user, rbac_list_users, rbac_remove_user, rbac_rotate_token, rbac_set_role,
)


def rbac_tools() -> List[MCPTool]:
    """Return five user-management tools; supplied tokens never enter results."""
    identifier = {'type': 'string'}
    role = {'type': 'string', 'enum': ['viewer', 'operator', 'admin']}
    return [
        MCPTool(name='ac_user_add', description='Add a user with a supplied secret token.',
                input_schema=schema({'user_id': identifier, 'display_name': identifier,
                                     'role': role, 'token': identifier},
                                    required=['user_id', 'display_name', 'role', 'token']),
                handler=rbac_add_user, annotations=NON_DESTRUCTIVE),
        MCPTool(name='ac_user_list', description='List user metadata without tokens or hashes.',
                input_schema=schema({}), handler=rbac_list_users, annotations=READ_ONLY),
        MCPTool(name='ac_user_remove', description='Remove a user and revoke its token.',
                input_schema=schema({'user_id': identifier}, required=['user_id']),
                handler=rbac_remove_user, annotations=DESTRUCTIVE),
        MCPTool(name='ac_user_set_role', description="Change an existing user's role.",
                input_schema=schema({'user_id': identifier, 'role': role},
                                    required=['user_id', 'role']),
                handler=rbac_set_role, annotations=DESTRUCTIVE),
        MCPTool(name='ac_user_rotate_token', description='Replace a token with a supplied secret.',
                input_schema=schema({'user_id': identifier, 'token': identifier},
                                    required=['user_id', 'token']),
                handler=rbac_rotate_token, annotations=DESTRUCTIVE),
    ]
