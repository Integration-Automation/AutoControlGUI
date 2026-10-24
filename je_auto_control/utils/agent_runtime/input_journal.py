"""Durable resource witnesses prevent input transfer after an unreviewed host crash."""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached


class InputJournal:
    """Write before native dispatch or input ACK; callers must hold the resource OS lock."""

    def __init__(self, resource: Path) -> None:
        self.path = resource.with_suffix(resource.suffix + ".journal")
        self.owner = uuid.uuid4().hex
        self._data: dict[str, Any] = {}

    def read(self) -> dict:
        """Return a bounded witness, treating corrupt or redirected state as requiring review."""
        if self.path.is_symlink():
            raise AgentTaskError("input recovery witness cannot be a symlink")
        if not self.path.exists():
            return {}
        try:
            if self.path.stat().st_size > 65536:
                raise ValueError("oversize input witness")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unknown input witness")
            self._validate_witness(data)
            return data
        except AgentTaskError:
            raise
        except (OSError, ValueError) as error:
            raise AgentTaskError("input recovery witness requires operator review") from error

    def _validate_witness(self, data: dict) -> None:
        if {"remote_protocol", "remote_effect", "remote_device", "recovery_epoch"} & data.keys():
            raise AgentTaskError("remote input witness requires its device-specific recovery protocol")

    def acquire(self) -> None:
        """Refuse a previous host's unfinished ownership rather than replaying its input."""
        previous = self.read()
        if previous.get("owner") or previous.get("in_flight") or previous.get("held"):
            raise AgentTaskError("input resource requires explicit crash recovery before acquisition")
        self._data = {"version": 1, "owner": self.owner, "in_flight": None, "held": {},
                      "review": previous.get("review")}
        self._write()

    def update(self, held: dict, operation: str | None = None) -> None:
        """Persist only owned release data and the outstanding operation marker."""
        self._data.update(held={} if not any(held.values()) else detached(held), in_flight=operation)
        self._write()

    def release(self) -> None:
        """Clear ownership only after confirmed process retirement and empty input ledger."""
        self._data.update(owner=None, held={}, in_flight=None)
        self._write()

    def recover(self, note: str, probe: Callable[[], None], actor: str) -> dict:
        """Clear stale input only after explicit review and a trusted no-held-input probe."""
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise AgentTaskError("crash recovery requires an operator review note (1-2000 characters)")
        previous = self.read()
        probe()
        self._data = {"version": 1, "owner": None, "held": {}, "in_flight": None,
                      "review": {"at": time.time(), "actor": actor, "note": note,
                                 "previous_owner": previous.get("owner")}}
        self._write()
        return {"recovered": True, "review": self._data["review"]}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".input-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            from je_auto_control.utils.json_store.json_store import _replace
            _replace(temporary, str(self.path))
            self.path.chmod(0o600)
        finally:
            Path(temporary).unlink(missing_ok=True)
        if os.name != "nt":
            descriptor = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
