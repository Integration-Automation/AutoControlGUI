"""Host-only input recovery checks never replay persisted keys or signal persisted PIDs."""
from __future__ import annotations

import ctypes
import sys
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.rbac.authorization import current_authorization, AuthorizationError
from je_auto_control.utils.rbac.users import Capability


def no_held_input() -> None:
    """Check an unlocked Windows desktop; other platforms require a trusted host adapter."""
    if sys.platform != "win32":
        raise AgentTaskError("this platform requires a trusted no-held-input recovery adapter")
    from je_auto_control.utils.agent_runtime.activity_windows import _interactive
    if not _interactive():
        raise AgentTaskError("unlock the interactive desktop before input recovery")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user.GetAsyncKeyState.restype = ctypes.c_short
    if any(user.GetAsyncKeyState(code) & 0x8000 for code in range(1, 256)):
        raise AgentTaskError("release held keys and mouse buttons manually before input recovery")


def recover_target(runtime: Any, target: str, note: str) -> dict:
    """Require host authority and a registered target's explicit recovery implementation."""
    owner = current_authorization()
    if owner is not None and not owner.allows(Capability.MANAGE_HOSTS):
        raise AuthorizationError("input crash recovery requires manage_hosts")
    adapter = runtime._targets.get(target)
    recover = getattr(adapter, "recover", None)
    if recover is None:
        raise AgentTaskError("target has no host-reviewed crash recovery adapter")
    return recover(note, actor=owner.user_id if owner is not None else "local-host")
