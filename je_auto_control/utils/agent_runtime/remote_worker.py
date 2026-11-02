"""Owned remote SDK worker with closed RPC, refreshed authority and ACK-gated finite effects."""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from contextlib import ExitStack
from dataclasses import replace
from typing import Any, Callable, Protocol

from je_auto_control.utils.agent_runtime.context import TaskOperation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, detached
from je_auto_control.utils.agent_runtime.parent_watch import start_parent_watch
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, durable_payload
from je_auto_control.utils.agent_runtime.remote_effect import (
    PreparedRemoteAction, RemoteEffectController, remote_scope_key)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.dispatch import command_guard
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import capability_for_command
from je_auto_control.utils.script_vars.execution import execution_scope

_LIMIT = 1_100_000


class RemoteDeviceAdapter(Protocol):
    """Trusted host SDK contract; no built-in Android/WDA implementation is assumed to satisfy it."""

    device: dict[str, str]

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Validate fixed host app/tool scope and trusted presence/held-input providers without input."""

    def observe(self) -> dict:
        """Read only reviewed device/app evidence; never dispatch input."""

    def prepare(self, name: str, arguments: dict) -> PreparedRemoteAction:
        """Read fresh identity, routing and security evidence and return one finite host-only call."""

    def checkpoint(self) -> None:
        """Refuse changed device/app scope, held input or physical takeover before every phase."""

    def set_takeover_handler(self, handler: Callable[[], None]) -> None:
        """Bind a trusted physical-activity notice; injected input must not masquerade as physical."""


class RemoteWorker:  # pylint: disable=too-many-instance-attributes  # reason: owned IPC and fixed scope have distinct state
    """Serial owned helper; adapters/configuration come from host code, never RPC or task options."""

    def __init__(self, source: Any, sink: Any, adapter: RemoteDeviceAdapter) -> None:
        self._source, self._sink, self._adapter = source, sink, adapter
        self._sink_lock = threading.Lock()
        self._takeover = threading.Event()
        self._config: str | None = None
        self._spec: AgentTaskSpec | None = None
        self._authority = DeferredAuthorization()
        self._controller: RemoteEffectController | None = None
        self._request_id = ""
        self._ready = False
        self._expires = 0.0
        adapter.set_takeover_handler(self.notify_physical_input)

    def _send(self, payload: dict) -> None:
        packet = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(packet) > _LIMIT:
            raise AgentTaskError("remote worker packet exceeds its bound")
        with self._sink_lock:
            self._sink.write(packet)
            self._sink.flush()

    def notify_physical_input(self) -> None:
        """Latch trusted physical takeover; subsequent requests cannot clear it or resume input."""
        self._takeover.set()
        self._send({"control": "physical_input"})

    def _read(self) -> dict:
        line = self._source.readline(_LIMIT + 1)
        if not line or len(line) > _LIMIT or not line.endswith(b"\n"):
            raise AgentTaskError("remote worker request is missing or exceeds its bound")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AgentTaskError("remote worker requires a closed object")
        return value

    def _notify(self, event: dict) -> None:
        self._send({"id": self._request_id, "event": event})
        ack = self._read()
        if set(ack) != {"ack"} or ack["ack"] is not True:
            raise AgentTaskError("remote effect was not acknowledged by its owner")

    def run(self) -> None:
        """Close after every failed RPC; no retry, SDK cleanup write or replacement is attempted."""
        while True:
            self._request_id = ""
            try:
                request = self._read()
                self._validate_request(request)
                self._request_id = request["id"]
                result = self._dispatch(request["operation"], request["payload"])
                self._send({"id": self._request_id, "result": durable_payload(result)})
            except (AutoControlException, OSError, RuntimeError, TypeError, ValueError, LookupError) as error:
                # Device diagnostics can contain command arguments and secrets; publish only a fixed category.
                if self._request_id:
                    self._send({"id": self._request_id, "error": "remote operation failed: " + type(error).__name__,
                                "error_type": type(error).__name__})
                return

    @staticmethod
    def _validate_request(request: dict) -> None:
        if (set(request) != {"id", "operation", "payload"} or not isinstance(request["id"], str)
                or re.fullmatch("[0-9a-f]{32}", request["id"]) is None):
            raise AgentTaskError("remote worker request has an invalid identity")
        if not isinstance(request["operation"], str) or not isinstance(request["payload"], dict):
            raise AgentTaskError("remote worker request has invalid operation fields")

    def _dispatch(self, operation: str, payload: dict) -> Any:
        if operation in {"bootstrap", "remote_capabilities"}:
            if payload:
                raise AgentTaskError("remote worker negotiation accepts no configuration")
            return {"protocol": 1} if operation == "bootstrap" else {"remote_effect_protocol": 1}
        if operation == "configure":
            self._configure(payload)
        if self._spec is None or self._controller is None:
            raise AgentTaskError("remote worker is not configured")
        self._expires = time.monotonic() + self._spec.budget.action_seconds
        with ExitStack() as stack:
            stack.enter_context(self._authority.scope())
            stack.enter_context(command_guard(self._guard))
            stack.enter_context(execution_scope(dict(self._spec.inputs)))
            stack.enter_context(operation_scope(TaskOperation(self._spec, self._checkpoint, self._authority.context)))
            return self._operation(operation, payload)

    def _configure(self, payload: dict) -> None:
        if set(payload) != {"spec", "owner", "remote_guard"}:
            raise AgentTaskError("remote worker configuration has unreviewed fields")
        if not isinstance(payload["owner"], dict):
            raise AgentTaskError("remote worker owner must be an explicit host identity object")
        config = detached({"spec": payload["spec"], "owner": payload["owner"]})
        key = remote_scope_key(config)
        if self._config is not None:
            if (self._config != key or self._controller is None
                    or not self._controller.matches(payload["remote_guard"])):
                raise AgentTaskError("remote worker configuration cannot replace its owner or controller")
            return
        spec = AgentTaskSpec.from_dict(config["spec"])
        TaskPolicy(spec)
        owner = AuthorizationContext(**config["owner"]) if config["owner"] else None
        controller = RemoteEffectController(payload["remote_guard"], self._adapter.device)
        self._config, self._spec = key, spec
        self._authority, self._controller = DeferredAuthorization(owner), controller

    def _checkpoint(self) -> None:
        if time.monotonic() >= self._expires:
            raise AgentTaskError("remote operation deadline exhausted")
        if self._takeover.is_set():
            raise AgentHumanReview("physical input requires explicit remote-device review")
        with self._authority.scope():
            self._adapter.checkpoint()

    def _guard(self, name: str, arguments: Any) -> None:
        self._checkpoint()
        if self._spec is None:
            raise AgentTaskError("remote worker lost its managed scope")
        with self._authority.scope():
            TaskPolicy(self._spec).check(name, arguments)
            owner, needed = current_authorization(), capability_for_command(name)
            if owner is not None and not owner.allows(needed):
                raise AuthorizationError("remote command is no longer authorized", capability=needed)

    def _perform(self, action: PreparedRemoteAction) -> Any:
        if not isinstance(action, PreparedRemoteAction) or self._controller is None:
            raise AgentTaskError("remote adapter did not prepare a finite action")

        def invoke() -> Any:
            with self._authority.scope():
                return action.invoke()

        return self._controller.perform(replace(action, invoke=invoke), self._notify, self._checkpoint)

    def _ready_adapter(self) -> dict:
        if self._spec is None:
            raise AgentTaskError("remote worker has no task specification")
        ready, reason = self._adapter.ready(self._spec)
        if not isinstance(ready, bool) or not isinstance(reason, str):
            raise AgentTaskError("remote adapter returned invalid readiness")
        self._ready = ready
        if ready:
            self._checkpoint()
        return {"ready": ready, "reason": reason}

    def _operation(self, operation: str, payload: dict) -> Any:
        if operation == "configure":
            return self._ready_adapter()
        if not self._ready:
            raise AgentTaskError("remote adapter is not ready")
        self._checkpoint()
        if operation == "observe" and not payload:
            return self._adapter.observe()
        if operation != "perform" or set(payload) != {"tool", "arguments"} or self._controller is None:
            raise AgentTaskError("remote worker operation is outside the finite protocol")
        self._guard(payload["tool"], payload["arguments"])
        action = self._adapter.prepare(payload["tool"], detached(payload["arguments"]))
        return self._perform(action)


def serve_remote_worker(factory: Callable[[], RemoteDeviceAdapter]) -> None:
    """Start parent retirement monitoring before constructing an explicit trusted host SDK adapter."""
    start_parent_watch()
    RemoteWorker(sys.stdin.buffer, sys.stdout.buffer, factory()).run()
