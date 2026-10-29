"""Choose each helper's owned channel: local pipes, or the Linux owner service the host bound."""
from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

# Installed by host management beside the service manifest it mirrors. Never taken
# from a task, a model, a request or the environment.
BINDING_PATH = "/etc/je_auto_control/owner_service.json"
_BINDING_BYTES = 65536


class HelperChannel(Protocol):
    """What every consumer may use: one serial request, an idempotent close and retirement."""

    @property
    def retired(self) -> bool:
        """True only once the helper is proven settled."""

    def request(self, operation: str, payload: Any, *, timeout: float, check: Callable[[], None] = ...,
                on_event: Callable[[dict], None] | None = None) -> Any:
        """Send one operation and return its reply."""

    def close(self) -> None:
        """Retire the helper."""


@dataclass(frozen=True)
class OwnerServiceBinding:
    """The service endpoint and the reviewed helper argv each manifest policy launches."""

    endpoint: str
    policies: Mapping[tuple[str, ...], int]


def _trusted(status: os.stat_result) -> bool:
    """Root-owned regular file that nobody else may rewrite."""
    return stat.S_ISREG(status.st_mode) and status.st_uid == 0 and not status.st_mode & 0o022


def _argv(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(part, str) and part for part in value):
        raise AgentTaskError("owner service binding row needs a non-empty argv of strings")
    return tuple(value)


def _policy_id(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 32:
        raise AgentTaskError("owner service binding policy must be an integer from 0 to 31")
    return value


def _policy_row(row: Any) -> tuple[tuple[str, ...], int]:
    if not isinstance(row, dict) or set(row) != {"argv", "policy"}:
        raise AgentTaskError("owner service binding rows hold exactly argv and policy")
    return _argv(row["argv"]), _policy_id(row["policy"])


def _policy_rows(rows: Any) -> dict[tuple[str, ...], int]:
    if not isinstance(rows, list) or not rows:
        raise AgentTaskError("owner service binding needs a non-empty policy table")
    policies: dict[tuple[str, ...], int] = {}
    for row in rows:
        argv, policy = _policy_row(row)
        if argv in policies:
            raise AgentTaskError("owner service binding lists one helper argv twice")
        policies[argv] = policy
    return policies


def _endpoint(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\0" in value or len(value) > 107:
        raise AgentTaskError("owner service endpoint must be an absolute socket path")
    return value


def _binding_document(path: str, status: os.stat_result) -> Any:
    if not _trusted(status) or status.st_size > _BINDING_BYTES:
        raise AgentTaskError("owner service binding must be a small root-owned file nobody else can write")
    try:
        with open(path, "rb") as handle:
            return json.loads(handle.read(_BINDING_BYTES + 1))
    except (OSError, ValueError) as error:
        raise AgentTaskError("owner service binding is not readable JSON") from error


def load_binding(path: str = BINDING_PATH) -> OwnerServiceBinding | None:
    """Read the host's binding; absent means none, anything untrusted or malformed refuses."""
    try:
        status = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise AgentTaskError(f"owner service binding is unreadable: {type(error).__name__}") from error
    data = _binding_document(path, status)
    if not isinstance(data, dict) or set(data) != {"endpoint", "policies"}:
        raise AgentTaskError("owner service binding holds exactly endpoint and policies")
    return OwnerServiceBinding(_endpoint(data["endpoint"]), _policy_rows(data["policies"]))


def _endpoint_reachable(endpoint: str) -> bool:
    import socket
    family, kind = getattr(socket, "AF_UNIX", None), getattr(socket, "SOCK_SEQPACKET", None)
    if family is None or kind is None:
        return False
    with socket.socket(family, kind) as probe:
        probe.settimeout(0.5)
        try:
            probe.connect(endpoint)
        except OSError:
            return False
    return True


def helper_containment() -> dict[str, Any]:
    """Describe how this host owns helper processes, without launching one.

    ``status`` separates what is not supported, not configured, refused, unreachable
    and merely reachable. Reaching the service is not containment evidence, so
    ``native_evidence`` is always ``not_recorded``: only protected acceptance records it.
    """
    result: dict[str, Any] = {"native_evidence": "not_recorded"}
    if sys.platform == "win32":
        return {**result, "mode": "local", "intended_containment": "windows_job_object", "status": "not_probed"}
    if not sys.platform.startswith("linux"):
        return {**result, "mode": "local", "intended_containment": "process_group", "status": "not_supported"}
    try:
        binding = load_binding()
    except AgentTaskError as error:
        return {**result, "mode": "owner_service", "intended_containment": "owner_service_cgroup",
                "status": "binding_refused", "reason": str(error)}
    if binding is None:
        return {**result, "mode": "local", "intended_containment": "process_group", "status": "not_configured"}
    status = "reachable_unverified" if _endpoint_reachable(binding.endpoint) else "unreachable"
    return {**result, "mode": "owner_service", "intended_containment": "owner_service_cgroup", "status": status,
            "policies": len(binding.policies)}


def owned_channel(argv: Sequence[str], *, on_control: Callable[[str], None] | None = None,
                  nested: Any = None) -> HelperChannel:
    """Return the channel that owns this helper.

    Linux with a host binding launches only through the owner service, and only an
    argv the binding lists exactly; there is no fallback to a local process. A helper
    started nested-capable passes the ``NestedGrant`` it read from fd 4, so its own
    helpers become child leases of its record. Every other case keeps the local
    ``OwnedChannel``, which has no nested form.
    """
    if sys.platform.startswith("linux"):
        binding = load_binding()
        if binding is not None:
            policy = binding.policies.get(tuple(argv))
            if policy is None:
                raise AgentTaskError("owner service binding has no policy for this helper")
            from je_auto_control.utils.agent_runtime.helper_owner_linux import (
                OwnerServiceChannel, SeqpacketTransport)
            return OwnerServiceChannel(SeqpacketTransport(binding.endpoint), policy, (), on_control=on_control,
                                       parent=nested)
    if nested is not None:
        raise AgentTaskError("a nested grant needs the Linux owner service")
    from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
    return OwnedChannel(argv, on_control=on_control)
