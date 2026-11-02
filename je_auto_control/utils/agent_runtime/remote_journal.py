"""Fence remote effects durably; retiring a local writer never certifies a remote device idle."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.input_journal import InputJournal
from je_auto_control.utils.agent_runtime.models import detached


def _token(value: object, label: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 256
            or any(ord(char) < 33 or ord(char) > 126 for char in value)):
        raise AgentTaskError(f"remote {label} must be a bounded plain identity token")
    return value


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum)


def device_identity(platform: str, physical_id: str) -> dict[str, str]:
    """Bind an adapter-proven physical device, without guessing serial normalization."""
    if platform not in ("android", "ios"):
        raise AgentTaskError("remote device platform must be android or ios")
    return {"platform": platform, "physical_id": _token(physical_id, "device identity")}


def device_resource(device: dict[str, str]) -> Path:
    """Share one physical-device resource across profiles, apps and runtime databases."""
    identity = device_identity(**device)
    encoded = json.dumps([identity["platform"], identity["physical_id"]]).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return Path.home() / ".je_auto_control" / "remote_input_ownership" / (digest + ".lock")


class RemoteInputJournal(InputJournal):
    """Host-held remote guard; callbacks persist before OwnedChannel acknowledges the helper."""

    def __init__(self, resource: Path, device: dict[str, str]) -> None:
        super().__init__(resource)
        self.device = device_identity(**device)

    def _validate_witness(self, data: dict) -> None:
        self._validate_header(data)
        if not _integer(data["next_sequence"], 1, 2**53):
            raise AgentTaskError("remote input witness has an invalid sequence")
        if data["held"] != {} or data["in_flight"] not in (None, "configure", "observe", "perform"):
            raise AgentTaskError("remote input witness has incompatible operation state")
        if data["owner"] is not None:
            _token(data["owner"], "controller")
        if data["recovery_epoch"] is not None:
            _token(data["recovery_epoch"], "recovery epoch")
            if data["remote_effect"] is None:
                raise AgentTaskError("remote recovery baseline has no matching effect")
        if data["remote_effect"] is not None:
            if data["in_flight"] != "perform":
                raise AgentTaskError("remote effect witness has no matching perform operation")
            self._validate_event(data["remote_effect"], "remote_begin", data)

    def _validate_header(self, data: dict) -> None:
        required = {"version", "remote_protocol", "remote_device", "owner", "held", "in_flight",
                    "review", "remote_effect", "next_sequence", "recovery_epoch"}
        if (set(data) != required or not _integer(data["version"], 1, 1)
                or not _integer(data["remote_protocol"], 1, 1) or data["remote_device"] != self.device):
            raise AgentTaskError("remote input witness is incompatible with this device")

    def _fresh(self, review: dict | None = None) -> dict:
        return {"version": 1, "remote_protocol": 1, "remote_device": detached(self.device),
                "owner": None, "held": {}, "in_flight": None, "review": review,
                "remote_effect": None, "next_sequence": 1, "recovery_epoch": None}

    @property
    def pending(self) -> bool:
        """Whether any acknowledged remote effect still lacks a matching end event."""
        return self._data.get("remote_effect") is not None

    @property
    def sequence(self) -> int:
        """Return the next exact sequence for this controller generation."""
        return self._data["next_sequence"]

    def acquire(self) -> None:
        """Never discard another controller, outstanding operation or recovery baseline."""
        previous = self.read()
        if previous.get("owner") or previous.get("in_flight") or previous.get("remote_effect"):
            raise AgentTaskError("remote device requires explicit crash recovery before acquisition")
        self._data = self._fresh(previous.get("review"))
        self._data["owner"] = self.owner
        self._write()

    def update(self, held: dict, operation: str | None = None) -> None:
        """Keep the remote marker intact; desktop release data is never valid here."""
        if held or operation not in (None, "configure", "observe", "perform"):
            raise AgentTaskError("remote guard cannot record desktop input or an unknown operation")
        if self.pending and operation != "perform":
            raise AgentTaskError("remote effect must settle before its operation can change")
        self._data["in_flight"] = operation
        self._write()

    def _validate_event(self, event: dict, kind: str, state: dict) -> None:
        if (not isinstance(event, dict)
                or set(event) != {"kind", "controller", "device", "sequence", "epoch"}
                or event["kind"] != kind):
            raise AgentTaskError("remote effect event has an invalid shape")
        if (event["controller"] != state["owner"] or event["device"] != self.device
                or not _integer(event["sequence"], state["next_sequence"], state["next_sequence"])
                or state["owner"] is None):
            raise AgentTaskError("remote effect event does not match its controller, device or sequence")
        _token(event["epoch"], "effect epoch")

    def consume(self, event: dict) -> None:
        """Persist a matched begin/end before returning permission to acknowledge it."""
        kind = event.get("kind")
        if kind not in ("remote_begin", "remote_end") or self._data.get("in_flight") != "perform":
            raise AgentTaskError("remote effects are only allowed during a managed perform request")
        self._validate_event(event, kind, self._data)
        if kind == "remote_begin":
            if self.pending or self.sequence >= 2**53:
                raise AgentTaskError("remote device already has an unsettled effect")
            self._data["remote_effect"] = detached(event)
        else:
            pending = self._data.get("remote_effect")
            if pending is None or pending["epoch"] != event["epoch"]:
                raise AgentTaskError("remote end event does not settle its recorded effect")
            self._data.update(remote_effect=None, next_sequence=self.sequence + 1)
        self._write()

    def release(self) -> None:
        """Called only after local retirement; unknown device effects retain the witness."""
        if self.pending:
            raise AgentTaskError("remote device effect is unconfirmed; resource remains quarantined")
        self._data.update(owner=None, in_flight=None)
        self._write()

    def recover(self, note: str, probe: Callable[[], object], actor: str) -> dict:
        """Require a trusted post-retirement epoch change invalidating all old commands.

        The host probe must certify this physical device, all old writers retired,
        and an epoch whose change invalidates old commands without replay. A fresh
        baseline is sampled AFTER writer retirement, never from a pre-input event.
        No SDK adapter is assumed to provide this proof automatically.
        """
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise AgentTaskError("remote recovery requires an operator review note (1-2000 characters)")
        previous = self.read()
        epoch = self._recovery_evidence(probe)
        if previous.get("remote_effect"):
            baseline = previous.get("recovery_epoch")
            if baseline is None:
                previous["recovery_epoch"] = epoch
                self._data = previous
                self._write()
            if baseline is None or baseline == epoch:
                return {"recovered": False, "phase": "awaiting_new_device_epoch"}
        review = {"at": time.time(), "actor": actor, "note": note, "previous_owner": previous.get("owner")}
        self._data = self._fresh(review)
        self._write()
        return {"recovered": True, "review": detached(review)}

    def _recovery_evidence(self, probe: Callable[[], object]) -> str:
        evidence = probe()
        if (not isinstance(evidence, dict) or set(evidence) != {"device", "epoch", "writers_retired"}
                or evidence["device"] != self.device or evidence["writers_retired"] is not True):
            raise AgentTaskError("remote recovery lacks trusted device and writer-retirement evidence")
        return _token(evidence["epoch"], "recovery epoch")
