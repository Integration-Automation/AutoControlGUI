"""Bracket trusted SDK calls with durable host ACKs and explicit remote settlement evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.remote_journal import _integer, _token, device_identity


def remote_scope_key(binding: dict) -> str:
    """Compare JSON types exactly, including bool/int/float distinctions in reviewed task inputs."""
    return json.dumps(binding, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


@dataclass(frozen=True)
class PreparedRemoteAction:
    """Host-only finite call; preparation is read-only and never confers model execution authority."""

    device: dict[str, str]
    epoch: str
    invoke: Callable[[], Any] = field(repr=False)
    settle: Callable[[], dict] = field(repr=False)


class RemoteEffectController:
    """One configured SDK writer; missing ACK or settlement poisons this controller permanently."""

    def __init__(self, guard: dict, device: dict[str, str]) -> None:
        self.device = device_identity(**device)
        if (not isinstance(guard, dict) or set(guard) != {"controller", "device", "next_sequence"}
                or guard["device"] != self.device or not _integer(guard["next_sequence"], 1, 2**53 - 1)):
            raise AgentTaskError("remote worker requires a matching closed controller guard")
        self.owner = _token(guard["controller"], "controller")
        self.sequence = guard["next_sequence"]
        self._pending = False

    def matches(self, guard: dict) -> bool:
        """Reconfiguration may only refresh the exact live controller, device and next sequence."""
        return (isinstance(guard, dict) and _integer(guard.get("next_sequence"), 1, 2**53 - 1)
                and guard == {"controller": self.owner, "device": self.device, "next_sequence": self.sequence})

    def perform(self, action: PreparedRemoteAction, notify: Callable[[dict], None],
                check: Callable[[], None]) -> Any:
        """Invoke once after begin ACK; never infer remote settlement from local return or failure."""
        if self._pending:
            raise AgentTaskError("remote controller requires explicit effect recovery")
        if (not isinstance(action, PreparedRemoteAction) or action.device != self.device
                or not callable(action.invoke) or not callable(action.settle) or self.sequence >= 2**53):
            raise AgentTaskError("remote action does not match a usable prepared controller")
        epoch = _token(action.epoch, "effect epoch")
        event = {"controller": self.owner, "device": detached(self.device), "sequence": self.sequence, "epoch": epoch}
        check()
        self._pending = True
        notify({**event, "kind": "remote_begin"})
        check()
        result = action.invoke()
        proof = action.settle()
        _require_settlement(proof, self.device, epoch)
        check()
        notify({**event, "kind": "remote_end"})
        self.sequence += 1
        self._pending = False
        return result


def _require_settlement(proof: object, device: dict[str, str], epoch: str) -> None:
    # Only a reviewed SDK provider can certify no held input and no queued old writes on this device.
    if (not isinstance(proof, dict) or set(proof) != {"device", "epoch", "inputs_released", "queue_empty"}
            or proof["device"] != device or proof["epoch"] != epoch):
        raise AgentTaskError("remote action lacks matching trusted settlement evidence")
    if proof["inputs_released"] is not True or proof["queue_empty"] is not True:
        raise AgentTaskError("remote action input or queued writes remain unconfirmed")
