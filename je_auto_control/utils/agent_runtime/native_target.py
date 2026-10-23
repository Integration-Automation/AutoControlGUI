"""Native desktop proxy with private IPC, host input ledger and cross-database ownership."""
from __future__ import annotations

import ctypes
import hashlib
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Sequence

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.input_ledger import InputLedger
from je_auto_control.utils.agent_runtime.input_journal import InputJournal
from je_auto_control.utils.agent_runtime.native_recovery import no_held_input
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.target_config import AgentTargetProfile
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

    def __init__(self, *, argv: Sequence[str] | None = None, resource_path: Path | None = None,
                 recovery_probe: Callable[[], None] = no_held_input, profile: dict | None = None) -> None:
        self._profile = AgentTargetProfile.from_dict(profile) if profile is not None else None
        self._argv = tuple(argv) if argv is not None else (
            sys.executable, "-u", "-m", "je_auto_control.utils.agent_runtime.native_worker")
        self._resource_path = resource_path
        self._resource: RuntimeLock | None = None
        self._journal: InputJournal | None = None
        self._recovery_probe = recovery_probe
        self._pending: str | None = None
        self._channel: OwnedChannel | None = None
        self._ledger = InputLedger()
        self._takeover: Any = None
        self._takeover_sent = threading.Event()

    def _ensure(self) -> OwnedChannel:
        if self._resource is None:
            path = self._resource_path or _desktop_lock_path()
            resource = RuntimeLock(path)
            journal = InputJournal(path)
            try:
                journal.acquire()
            except BaseException:  # reason: failed recovery gate cannot retain the newly acquired OS lock
                resource.close()
                raise
            self._resource, self._journal = resource, journal
        if self._channel is None or self._channel.retired:
            if not self._ledger.empty:
                raise AgentTaskError("native input cleanup is required before another operation")
            self._takeover_sent.clear()
            context = current_operation()
            self._channel = self._launch(context.checkpoint if context is not None else lambda: None, self._control)
        return self._channel

    def _launch(self, check: Callable[[], None], control: Callable[[str], None] | None = None) -> OwnedChannel:
        self._channel = OwnedChannel(self._argv, on_control=control)
        reply = self._channel.request("bootstrap", {}, timeout=15, check=check)
        if not isinstance(reply, dict) or type(reply.get("protocol")) is not int or reply["protocol"] != 1:
            self._channel.close()
            raise AgentTaskError("native helper bootstrap protocol is incompatible")
        return self._channel

    @property
    def can_reobserve(self) -> bool:
        """Allow pre-dispatch replanning only with no held input and a settled live channel."""
        return (self._channel is not None and not self._channel.retired
                and self._ledger.empty and self._pending is None)

    def _control(self, _kind: str) -> None:
        if self._takeover is None or self._takeover_sent.is_set():
            return
        self._takeover_sent.set()
        # The reader must stay available while cancellation/cleanup retires
        # its channel; it cannot join itself from a control notification.
        threading.Thread(target=self._takeover, name="AgentTakeover", daemon=True).start()

    def _request(self, operation: str, payload: dict) -> Any:
        context = current_operation()
        if context is None:
            raise AgentTaskError("native targets require an explicitly managed operation scope")
        context.checkpoint()
        channel = self._ensure()
        self._pending = operation
        self._persist()
        result = channel.request(operation, payload, timeout=context.spec.budget.action_seconds,
                                 check=context.checkpoint, on_event=self._input)
        self._pending = None
        self._persist()
        return result

    def _persist(self) -> None:
        if self._journal is not None:
            self._journal.update(self._ledger.snapshot(), self._pending)

    def _input(self, event: dict, *, cleanup: bool = False) -> None:
        self._ledger.consume(event, cleanup=cleanup)
        self._persist()

    def recover(self, note: str, *, actor: str) -> dict:
        """Review a stale witness while exclusively owning the resource; never replay old input."""
        path = self._resource_path or _desktop_lock_path()
        lock = RuntimeLock(path)
        try:
            return InputJournal(path).recover(note, self._recovery_probe, actor)
        finally:
            lock.close()

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Configure the owned helper only after the runtime has acquired its target lease."""
        context = current_operation()
        if context is None or context.spec != spec:
            raise AgentTaskError("native target scope does not match its owner")
        if self._profile is not None:
            from je_auto_control.utils.agent_runtime.target_config import check_host_platform
            check_host_platform(self._profile)
            self._profile.check(spec)
        owner = context.owner
        self._takeover = context.takeover
        identity = {"user_id": owner.user_id, "role": owner.role,
                    "store_path": owner.store_path} if owner is not None else {}
        payload = {"spec": spec.to_dict(), "owner": identity}
        if self._profile is not None:
            payload["profile"] = self._profile.to_dict()
        result = self._request("configure", payload)
        return bool(result["ready"]), str(result.get("reason", ""))

    def observe(self) -> dict[str, Any]:
        """Capture in the helper, enforcing the host's live operation deadline."""
        return self._request("observe", {})

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute an authorized command in the helper, retaining input ownership in the host."""
        if name == "AC_workflow_open":
            from je_auto_control.utils.agent_runtime.workflow_desktop import workflow_open
            self._ensure()
            self._pending = "launch_document"
            self._persist()
            result = workflow_open(**arguments)
            self._pending = None
            self._persist()
            return result
        return self._request("perform", {"tool": name, "arguments": arguments})

    def cleanup(self) -> None:
        """Reap native calls and release only host-recorded keys/buttons before input transfer."""
        channel = self._channel
        if not self._ledger.empty:
            if channel is None or channel.retired:
                channel = self._launch(lambda: None)
            channel.request("cleanup", self._ledger.snapshot(), timeout=3, check=lambda: None,
                            on_event=lambda event: self._input(event, cleanup=True))
        if channel is not None:
            channel.close()
        self._channel = None
        if not self._ledger.empty:
            raise AgentTaskError("native input cleanup has not been confirmed")
        if self._journal is not None:
            self._journal.release()
            self._journal = None
        self._pending = None
        if self._resource is not None:
            self._resource.close()
            self._resource = None
