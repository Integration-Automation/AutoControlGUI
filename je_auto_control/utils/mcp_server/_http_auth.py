"""HTTP caller authentication, shared-token compatibility and session ownership."""
from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from je_auto_control.utils.http_headers import bearer_challenge
from je_auto_control.utils.rbac.authorization import authenticate_header
from je_auto_control.utils.rbac.users import UserAuthError

if TYPE_CHECKING:
    from je_auto_control.utils.mcp_server.http_transport import _MCPHttpHandler
    from je_auto_control.utils.mcp_server.http_sessions import HttpSession


def caller_allowed(handler: _MCPHttpHandler) -> bool:
    """Authenticate one HTTP request without storing bearer tokens."""
    handler._authorization = None
    if not handler._origin_allowed():
        handler._send_json({'error': 'origin not allowed'}, status=403)
        return False
    store = handler.server.user_store  # type: ignore[attr-defined]
    expected = handler.server.auth_token  # type: ignore[attr-defined]
    if store is None and expected is None:
        return True
    header = handler.headers.get('Authorization')
    challenge = {'WWW-Authenticate': bearer_challenge('autocontrol-mcp', header)}
    if store is not None:
        try:
            handler._authorization = authenticate_header(header, store)
            return True
        except UserAuthError:
            handler._send_json({'error': 'invalid bearer token'}, status=401, extra_headers=challenge)
            return False
    scheme, _, provided = (header or '').strip().partition(' ')
    if scheme.lower() != 'bearer':
        handler._send_json({'error': 'missing bearer token'}, status=401, extra_headers=challenge)
        return False
    if not hmac.compare_digest(provided.strip().encode('utf-8'), expected.encode('utf-8')):
        handler._send_json({'error': 'invalid bearer token'}, status=401, extra_headers=challenge)
        return False
    return True


def session_allowed(handler: _MCPHttpHandler, session: HttpSession) -> bool:
    """Accept sessions only for the authenticated owner, or legacy anonymous use."""
    identity = handler._authorization
    if identity is None:
        return session.user_id is None
    return session.user_id == identity.user_id
