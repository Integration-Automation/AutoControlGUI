"""Native desktop proxy with private IPC, host input ledger and cross-database ownership."""
from __future__ import annotations

import ctypes
import hashlib
import os
import socket
import sys
from pathlib import Path
from typing import Any, Sequence

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.input_ledger import InputLedger
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.agent_runtime.runtime_lock import RuntimeLock


def _desktop_lock_path() -> Path:
    if sys.platform == "win32":
        session = ctypes.c_uint32()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.ProcessIdToSessionId.argtypes = (ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
        kernel.ProcessIdToSessionId.restype = ctypes.c_int
        if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            raise AgentTaskError("cannot identify the interactive input session")
        identity = f"{socket.gethostname()}:{session.value}:{os.getlogin()}"
    else:
        # Conservative on POSIX: independently named displays for the same user
        # cannot accidentally acquire the same compositor's input concurrently.
        identity = f"{socket.gethostname()}:{os.getuid()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path.home() / ".je_auto_control" / "input_ownership" / (digest + ".lock")


class NativeDesktopTarget:
    """Only trusted host code may select an argv/resource path; neither is task/model input."""

    def __init__(self, *, argv: Sequence[str] | None = None, resource_path: Path | None = None) -> None:
        self._argv = tuple(argv) if argv is not None else (
            sys.executable, "-u", "-m", "je_auto_control.utils.agent_runtime.native_worker")
        self._resource_path = resource_path
        self._resource: RuntimeLock | None = None
        self._channel: OwnedChannel | None = None
        self._ledger = InputLedger()

    def _ensure(self) -> OwnedChannel:
        if self._resource is None:
            self._resource = RuntimeLock(self._resource_path or _desktop_lock_path())
        if self._channel is None or self._channel.retired:
            if not self._ledger.empty:
                raise AgentTaskError("native input cleanup is required before another operation")
            self._channel = OwnedChannel(self._argv)
        return self._channel

    def _request(self, operation: str, payload: dict) -> Any:
        context = current_operation()
        if context is None:
            raise AgentTaskError("native targets require an explicitly managed operation scope")
        context.checkpoint()
        channel = self._ensure()
        return channel.request(operation, payload, timeout=context.spec.budget.action_seconds,
                               check=context.checkpoint, on_event=self._ledger.consume)

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Configure the owned helper only after the runtime has acquired its target lease."""
        context = current_operation()
        if context is None or context.spec != spec:
            raise AgentTaskError("native target scope does not match its owner")
        owner = context.owner
        identity = {"user_id": owner.user_id, "role": owner.role,
                    "store_path": owner.store_path} if owner is not None else {}
        result = self._request("configure", {"spec": spec.to_dict(), "owner": identity})
        return bool(result["ready"]), str(result.get("reason", ""))

    def observe(self) -> dict[str, Any]:
        """Capture in the helper, enforcing the host's live operation deadline."""
        return self._request("observe", {})

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute an authorized command in the helper, retaining input ownership in the host."""
        return self._request("perform", {"tool": name, "arguments": arguments})

    def cleanup(self) -> None:
        """Reap native calls and release only host-recorded keys/buttons before input transfer."""
        channel = self._channel
        if not self._ledger.empty:
            if channel is None or channel.retired:
                channel = OwnedChannel(self._argv)
                self._channel = channel
            channel.request("cleanup", self._ledger.snapshot(), timeout=3, check=lambda: None,
                            on_event=lambda event: self._ledger.consume(event, cleanup=True))
        if channel is not None:
            channel.close()
        self._channel = None
        if not self._ledger.empty:
            raise AgentTaskError("native input cleanup has not been confirmed")
        if self._resource is not None:
            self._resource.close()
            self._resource = None
