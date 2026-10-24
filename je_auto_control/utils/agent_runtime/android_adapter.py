"""Bridge checked Android sessions into the owned worker only with explicit trusted device-control leases."""
from __future__ import annotations

import time
import uuid
from typing import Callable

from je_auto_control.utils.agent_runtime.android_action_result import AndroidActionResult
from je_auto_control.utils.agent_runtime.android_commands import ANDROID_INPUT_TOOLS
from je_auto_control.utils.agent_runtime.android_control import AndroidCommandLease, AndroidControlProvider
from je_auto_control.utils.agent_runtime.android_input_evidence import AndroidInputEvidence
from je_auto_control.utils.agent_runtime.android_session import AndroidDeviceSession, _remaining
from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentObservationStale, AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.remote_effect import PreparedRemoteAction, remote_scope_key
from je_auto_control.utils.agent_runtime.remote_journal import device_identity


class AndroidRemoteAdapter:
    """Internal finite ADB adapter; missing real device-control providers always withhold readiness."""

    def __init__(self, session: AndroidDeviceSession, *, control: AndroidControlProvider | None = None) -> None:
        self._session, self._control = session, control
        self._spec: AgentTaskSpec | None = None
        self._observed: AndroidInputEvidence | None = None

    @property
    def device(self) -> dict[str, str]:
        """Bind remote ownership to the physical device rather than the app or connection serial."""
        return device_identity("android", self._session.binding[0])

    def set_takeover_handler(self, handler: Callable[[], None]) -> None:
        """Forward only the explicitly configured provider's trusted physical-activity notices."""
        if self._control is not None:
            self._control.set_takeover_handler(handler)

    def checkpoint(self) -> None:
        """No local fallback can certify remote activity, held input or device fencing."""
        if self._control is None:
            raise AgentTaskError("Android requires a trusted device-control provider")
        self._control.checkpoint(self._session.binding)

    def _context(self) -> tuple[AgentTaskSpec, Callable[[], None]]:
        context = current_operation()
        if context is None:
            raise AgentTaskError("Android adapter requires its explicitly managed operation scope")
        if (self._spec is not None
                and remote_scope_key(context.spec.to_dict()) != remote_scope_key(self._spec.to_dict())):
            raise AgentTaskError("Android adapter cannot replace its configured task scope")
        return context.spec, context.checkpoint

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Validate exact host app/tools and require native checks plus real device-control authority."""
        current, check = self._context()
        if remote_scope_key(current.to_dict()) != remote_scope_key(spec.to_dict()):
            raise AgentTaskError("Android readiness does not match its managed task")
        if tuple(spec.apps) != (self._session.binding[1],) or not set(spec.allowed_tools) <= ANDROID_INPUT_TOOLS:
            return False, "Android requires its exact host-bound app and finite reviewed input tools"
        if self._control is None:
            return False, "Android trusted device fencing/presence/settlement provider is not configured"
        _, evidence = self._session.inspect_input(timeout=spec.budget.action_seconds, check=check)
        ready, reason = self._control.ready(evidence.snapshot, evidence, spec)
        if not isinstance(ready, bool) or not isinstance(reason, str):
            raise AgentTaskError("Android control provider returned invalid readiness")
        check()
        if ready:
            self._spec = spec
            self._observed = None
        return ready, reason

    def observe(self) -> dict:
        """Publish only current app identity/routing metadata; no screenshot, text or foreign window data."""
        spec, check = self._context()
        if self._spec is None:
            raise AgentTaskError("Android adapter is not ready")
        self.checkpoint()
        _, evidence = self._session.inspect_input(timeout=spec.budget.action_seconds, check=check)
        check()
        self._observed = evidence
        return {"identity": {**evidence.snapshot.identity(), "input_routing": evidence.input_sha256,
                             "input_policy": evidence.policy_sha256, "display_size": list(evidence.size)},
                "elements": [], "text": ""}

    def prepare(self, name: str, arguments: dict) -> PreparedRemoteAction:
        """Refuse stale evidence and return one finite call bound to a fresh trusted device lease."""
        spec, check = self._context()
        if self._spec is None or self._observed is None or self._control is None:
            raise AgentObservationStale("Android action requires a current checked observation")
        if name not in spec.allowed_tools:
            raise AgentTaskError("Android tool is outside its configured task")
        deadline = time.monotonic() + spec.budget.action_seconds
        arguments = detached(arguments)
        proposal = self._session.propose_checked(name, arguments, timeout=_remaining(deadline), check=check)
        if not _same_evidence(self._observed, proposal.input_evidence):
            raise AgentObservationStale("Android input identity, geometry or security changed since observation")
        request_id = uuid.uuid4().hex
        lease = self._control.lease(proposal, request_id)
        if (not isinstance(lease, AndroidCommandLease) or lease.proposal != proposal or lease.request_id != request_id):
            raise AgentTaskError("Android control lease does not match its exact prepared command")
        check()
        self._observed = None
        return _prepared_call(self._session, lease, name, arguments, deadline, check)


def _same_evidence(expected: AndroidInputEvidence, actual: AndroidInputEvidence | None) -> bool:
    return actual == expected


def _prepared_call(session: AndroidDeviceSession, lease: AndroidCommandLease, name: str,
                   arguments: dict, deadline: float, check: Callable[[], None]) -> PreparedRemoteAction:
    results: list[AndroidActionResult] = []
    invoked = False

    def checkpoint() -> None:
        check()
        lease.checkpoint()
        _remaining(deadline)

    def invoke() -> dict:
        nonlocal invoked
        if invoked:
            raise AgentTaskError("Android prepared commands cannot be replayed")
        invoked = True
        result = None
        checkpoint()
        with lease.device_fence():
            checkpoint()
            result = session.dispatch_checked(lease.proposal, name, arguments,
                                              timeout=_remaining(deadline), check=checkpoint)
        if result is None:
            raise AgentTaskError("Android device fence suppressed an unknown dispatch failure")
        results.append(result)
        return {"android_phase": result.phase, "may_have_effect": result.may_have_effect}

    def settle() -> dict:
        if len(results) != 1:
            raise AgentTaskError("Android settlement has no complete command result")
        proof = lease.settle(results[0])
        if (not isinstance(proof, dict)
                or set(proof) != {"device", "epoch", "inputs_released", "queue_empty", "request_id", "boot_id"}
                or proof["request_id"] != lease.request_id or proof["boot_id"] != lease.proposal.snapshot.boot_id):
            raise AgentTaskError("Android settlement does not match this command request and boot")
        return {key: value for key, value in proof.items() if key not in {"request_id", "boot_id"}}

    return PreparedRemoteAction(device_identity("android", lease.proposal.snapshot.physical_id),
                                lease.epoch, invoke, settle)
