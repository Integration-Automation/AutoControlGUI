"""Offline signing tools with separate private and public key paths."""
from typing import Any, Dict, List, Optional
from je_auto_control.utils.mcp_server.tools._base import (
    DESTRUCTIVE, MCPTool, NON_DESTRUCTIVE, READ_ONLY, schema,
)


def _create_signing_keypair(private_path: str, public_path: str) -> Dict[str, Any]:
    """Load the key generator lazily to avoid executor import cycles."""
    from je_auto_control.utils.executor.action_executor import _create_signing_keypair as create
    return create(private_path, public_path)


def _sign_action_file(path: str, key: Optional[str] = None, private_key_path: Optional[str] = None,
                      legacy_hmac: bool = False) -> Dict[str, Any]:
    """Forward explicitly configured signing parameters to the API adapter."""
    from je_auto_control.utils.executor.action_executor import _sign_action_file as sign
    return sign(path, key, private_key_path, legacy_hmac)


def _verify_action_file(path: str, key: Optional[str] = None, public_key_path: Optional[str] = None,
                        allow_legacy_hmac: bool = False,
                        raise_on_fail: bool = False) -> Dict[str, Any]:
    """Forward public verification and explicit legacy migration options."""
    from je_auto_control.utils.executor.action_executor import _verify_action_file as verify
    return verify(path, key, raise_on_fail, public_key_path, allow_legacy_hmac)


def signing_tools() -> List[MCPTool]:
    """Return key generation, signing and public-only verification tools."""
    return [
        MCPTool(
            name='ac_create_signing_keypair',
            description=('Create separate Ed25519 private/public PEM files '
                         'without overwriting keys.'),
            input_schema=schema({
                'private_path': {'type': 'string'}, 'public_path': {'type': 'string'},
            }, required=['private_path', 'public_path']),
            handler=_create_signing_keypair, annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name='ac_sign_action_file',
            description='Sign exact action-file bytes using an explicitly configured private key.',
            input_schema=schema({
                'path': {'type': 'string'}, 'private_key_path': {'type': 'string'},
                'key': {'type': 'string'}, 'legacy_hmac': {'type': 'boolean'},
            }, required=['path']),
            handler=_sign_action_file, annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name='ac_verify_action_file',
            description='Verify an action signature using a trusted public key only.',
            input_schema=schema({
                'path': {'type': 'string'}, 'public_key_path': {'type': 'string'},
                'key': {'type': 'string'}, 'allow_legacy_hmac': {'type': 'boolean'},
                'raise_on_fail': {'type': 'boolean'},
            }, required=['path']),
            handler=_verify_action_file, annotations=READ_ONLY,
        ),
    ]
