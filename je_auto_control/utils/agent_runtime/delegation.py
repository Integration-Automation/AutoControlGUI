"""Short-lived, authenticated principal forwarding across the local service boundary."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.authorization import AuthorizationContext
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

HEADER = "X-AutoControl-Principal"


def sign_principal(identity: AuthorizationContext, token: str, path: str) -> str:
    """Authenticate internal principal metadata; it is never an argument offered to a model."""
    payload = {"user_id": identity.user_id, "role": identity.role, "store_path": identity.store_path,
               "expires": time.time() + 30, "path": path}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode("ascii")
    signature = hmac.new(token.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + "." + signature


def verify_principal(header: str, token: str, path: str) -> AuthorizationContext:
    """Verify the bridge signature and refresh store-backed users before route authorization."""
    try:
        encoded, signature = header.split(".", 1)
        expected = hmac.new(token.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise AgentTaskError("invalid principal signature")
        data: dict[str, Any] = json.loads(base64.urlsafe_b64decode(encoded))
        if data.pop("path") != path or not time.time() <= data.pop("expires") <= time.time() + 31:
            raise AgentTaskError("expired or mismatched principal forwarding")
        context = AuthorizationContext(**data)
        with DeferredAuthorization(context).context_scope() as refreshed:
            if refreshed is None:
                raise AgentTaskError("missing principal")
            return refreshed
    except (ValueError, TypeError, KeyError) as error:
        raise AgentTaskError("invalid local principal forwarding") from error
