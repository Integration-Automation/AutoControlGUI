"""Internal owned remote-helper lifecycle, without assuming ADB or WDA retirement guarantees."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Sequence

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.owned_channel_factory import HelperChannel, owned_channel
from je_auto_control.utils.agent_runtime.remote_journal import RemoteInputJournal, device_identity, device_resource
from je_auto_control.utils.agent_runtime.remote_effect import remote_scope_key
from je_auto_control.utils.agent_runtime.runtime_lock import RuntimeLock
from je_auto_control.utils.agent_runtime.target_continuity import require_context_continuity


class NativeRemoteTarget:  # pylint: disable=too-many-instance-attributes  # reason: fixed config and owned resources differ
    """Trusted adapter prerequisite; no built-in device profile or SDK support is advertised."""

    def __init__(self, *, argv: Sequence[str], platform: str, physical_id: str,
                 recovery_probe: Callable[[], dict] | None = None, resource_path: Path | None = None) -> None:
        if not argv or any(not isinstance(part, str) or not part for part in argv):
            raise AgentTaskError("remote helper requires fixed trusted host arguments")
        self._device = device_identity(platform, physical_id)
        self._argv = tuple(argv)
        self._path = resource_path or device_resource(self._device)
        self._probe = recovery_probe
        self._resource: RuntimeLock | None = None
        self._journal: RemoteInputJournal | None = None
        self._channel: HelperChannel | None = None
        self._mutex = threading.RLock()
        self._bound: str | None = None
        self._takeover: Callable[[], None] | None = None
        self._takeover_sent = threading.Event()

    @property
    def can_reobserve(self) -> bool:
        """Unknown remote work never permits pre-dispatch replanning."""
        return (self._channel is not None and not self._channel.retired and self._journal is not None
                and not self._journal.pending and self._journal.read().get("in_flight") is None)

    def check_resume(self, spec: AgentTaskSpec, receipts: list[dict]) -> None:
        """An old finite UI prefix cannot establish a new device/app context."""
        connected = self._channel is not None and not self._channel.retired
        require_context_continuity(spec, receipts, connected, kind="desktop")

    def _ensure(self, check: Callable[[], None]) -> tuple[HelperChannel, RemoteInputJournal]:
        if self._resource is None:
            self._acquire()
        journal = self._journal
        if journal is None or journal.pending or journal.read().get("in_flight") is not None:
            raise AgentTaskError("remote device requires effect recovery before another request")
        if self._channel is not None and self._channel.retired:
            raise AgentTaskError("remote helper retired; explicit cleanup is required before replacement")
        if self._channel is None:
            self._launch(check)
        if self._channel is None:
            raise AgentTaskError("remote helper could not start")
        return self._channel, journal

    def _acquire(self) -> None:
        resource = RuntimeLock(self._path)
        journal = RemoteInputJournal(self._path, self._device)
        try:
            journal.acquire()
        except BaseException:  # reason: a failed acquisition cannot leak a new OS lock
            resource.close()
            raise
        self._resource, self._journal = resource, journal

    def _launch(self, check: Callable[[], None]) -> None:
        self._takeover_sent.clear()
        self._channel = owned_channel(self._argv, on_control=self._control)
        for operation, expected in (("bootstrap", {"protocol": 1}),
                                    ("remote_capabilities", {"remote_effect_protocol": 1})):
            reply = self._channel.request(operation, {}, timeout=15, check=check)
            if (not isinstance(reply, dict) or reply != expected
                    or any(not isinstance(value, int) or isinstance(value, bool) for value in reply.values())):
                self._channel.close()
                raise AgentTaskError("remote helper effect protocol is incompatible")

    def _control(self, _kind: str) -> None:
        if self._takeover is None:
            raise AgentHumanReview("physical input requires an explicit remote takeover handler")
        if not self._takeover_sent.is_set():
            self._takeover_sent.set()
            threading.Thread(target=self._takeover, name="RemoteTakeover", daemon=True).start()

    @staticmethod
    def _binding() -> dict:
        context = current_operation()
        if context is None:
            raise AgentTaskError("remote target has no managed owner")
        owner = context.owner
        identity = {"user_id": owner.user_id, "role": owner.role, "store_path": owner.store_path} if owner else {}
        return {"spec": context.spec.to_dict(), "owner": identity}

    def _request(self, operation: str, payload: dict) -> Any:
        with self._mutex:
            context = current_operation()
            if context is None:
                raise AgentTaskError("remote targets require an explicitly managed operation scope")
            context.checkpoint()
            if operation != "configure" and self._bound != remote_scope_key(self._binding()):
                raise AgentTaskError("remote helper scope does not match its configured owner")
            channel, journal = self._ensure(context.checkpoint)
            if operation == "configure":
                payload = {**payload, "remote_guard": {"controller": journal.owner,
                           "device": detached(self._device), "next_sequence": journal.sequence}}
            sequence = journal.sequence
            journal.update({}, operation)
            result = channel.request(operation, payload, timeout=context.spec.budget.action_seconds,
                                     check=context.checkpoint, on_event=journal.consume)
            if journal.pending or (operation == "perform" and sequence == journal.sequence):
                channel.close()
                raise AgentTaskError("remote helper did not settle its effect protocol")
            journal.update({})
            return result

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Send host identity guard only within this exact managed task scope."""
        with self._mutex:
            context = current_operation()
            if context is None or context.spec != spec:
                raise AgentTaskError("remote target scope does not match its owner")
            binding = self._binding()
            if self._bound is not None and remote_scope_key(binding) != self._bound:
                raise AgentTaskError("remote helper cannot replace its configured owner")
            self._takeover = context.takeover
            result = self._request("configure", binding)
            if not isinstance(result, dict) or not isinstance(result.get("ready"), bool):
                raise AgentTaskError("remote helper returned invalid readiness")
            if result["ready"]:
                self._bound = remote_scope_key(binding)
            return result["ready"], str(result.get("reason", ""))

    def observe(self) -> dict[str, Any]:
        """Read device evidence without granting permission for remote writes."""
        return self._request("observe", {})

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Require every remote operation to bracket its effects with durable events."""
        return self._request("perform", {"tool": name, "arguments": arguments})

    def cleanup(self) -> None:
        """Retire only the owned writer; leave unknown remote effects quarantined."""
        with self._mutex:
            if self._channel is not None:
                self._channel.close()
                self._channel = None
            self._bound = None
            if self._journal is not None:
                self._journal.release()
                self._journal = None
            if self._resource is not None:
                self._resource.close()
                self._resource = None

    def recover(self, note: str, *, actor: str) -> dict:
        """Review without replay; host-provided proof is mandatory even after host restart."""
        with self._mutex:
            if self._probe is None:
                raise AgentTaskError("remote device has no trusted recovery evidence provider")
            if self._channel is not None:
                self._channel.close()
                self._channel = None
                self._bound = None
            resource = self._resource or RuntimeLock(self._path)
            try:
                result = RemoteInputJournal(self._path, self._device).recover(note, self._probe, actor)
                if result["recovered"]:
                    self._journal = None
                    self._resource = None
                return result
            finally:
                if self._resource is None:
                    resource.close()
