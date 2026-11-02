"""Fresh isolated completion observations with live scope checks and permanent no-input helper contracts."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from je_auto_control.utils.agent_runtime.context import TaskOperation, current_operation, operation_scope
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization


def _identity(value: AuthorizationContext | None) -> tuple[str, str | None] | None:
    return (value.user_id, value.store_path) if value is not None else None


def _require_contract(reply: Any) -> None:
    # pylint: disable-next=unidiomatic-typecheck  # reason: exact protocol integer excludes boolean versions
    if (not isinstance(reply, dict) or type(reply.get("contract")) is not int
            or reply != {"contract": 1, "input_supported": False} or reply.get("input_supported") is not False):
        raise AgentTaskError("completion helper does not prove its read-only contract")


class ReadOnlyNativeTarget(NativeDesktopTarget):
    """Also refuse input ACKs on the host, preserving unexpected events as resource quarantine."""

    _worker_module = "je_auto_control.utils.agent_runtime.readonly_worker"

    def ready(self, spec: AgentTaskSpec) -> tuple[bool, str]:
        """Require the permanent read-only contract before any target configuration, including direct SDK use."""
        context = current_operation()
        if context is None or context.spec != spec:
            raise AgentTaskError("read-only target scope does not match its owner")
        _require_contract(self._request("readonly_capabilities", {}))
        return super().ready(spec)

    def perform(self, name: str, arguments: dict[str, Any]) -> Any:
        """Refuse host-side workflow launch/file tools as well as helper-dispatched input."""
        raise AgentTaskError("read-only target cannot perform tools")

    def recover(self, note: str, *, actor: str) -> dict:
        """Read-only observation cannot clear a previous owner's unknown input witness."""
        raise AgentTaskError("read-only target cannot recover input resources")

    def _input(self, event: dict, *, cleanup: bool = False) -> None:
        self._pending = "readonly_input_violation"
        try:
            self._ledger.consume(event, cleanup=cleanup)
        finally:
            self._persist()
        raise AgentTaskError("read-only helper attempted native input")

    def cleanup(self) -> None:
        """Retire a violating helper without injecting releases or clearing its resource witness."""
        if self._pending != "readonly_input_violation" and self._ledger.empty:
            super().cleanup()
            return
        if self._channel is not None:
            self._channel.close()
            self._channel = None
        if self._resource is not None:
            self._resource.close()
            self._resource = None
        raise AgentTaskError("read-only input violation requires explicit resource recovery")


class CompletionReader:
    """Expose fresh observe/verify calls only; closed views never launch replacement helpers."""

    def __init__(self, adapter: ReadOnlyNativeTarget, spec: AgentTaskSpec) -> None:
        parent = current_operation()
        if parent is None or parent.spec != spec:
            raise AgentTaskError("completion reader requires its exact managed operation scope")
        self._adapter, self._spec, self._parent = adapter, spec, parent
        self._authority = DeferredAuthorization.capture()
        self._policy = TaskPolicy(spec)
        self._closed = False
        self._retired = False

    def _check(self) -> None:
        if self._closed:
            raise AgentTaskError("completion reader is closed")
        with self._authority.scope():
            self._policy.validate_snapshot()
            self._parent.checkpoint()

    def _call(self, operation: str, body: dict) -> Any:
        if current_operation() is not self._parent:
            raise AgentTaskError("completion reader cannot be borrowed by another operation")
        actual, captured = current_authorization(), self._authority.context
        if _identity(actual) != _identity(captured):
            raise AgentTaskError("completion reader cannot be borrowed by another owner")
        self._check()
        with operation_scope(TaskOperation(self._spec, self._check, self._parent.owner)):
            # pylint: disable-next=protected-access  # reason: the closed view owns this private IPC endpoint
            result = self._adapter._request(operation, body)
        self._check()
        return result

    def observe(self) -> dict:
        """Return a fresh scoped observation with no historical-frame or replacement-context fallback."""
        return self._call("observe", {})

    def verify_browser(self, clause: Mapping[str, Any]) -> Any:
        """Read only an already supported pinned browser criterion; no browser is started here."""
        if not any(dict(item) == dict(clause) for item in self._spec.success_criteria if item.get("kind") == "browser"):
            raise AgentTaskError("browser completion criterion is not pinned to this reader")
        return self._call("verify_browser", {"clause": dict(clause)})

    @property
    def retired(self) -> bool:
        """Confirm this view's successful helper/input cleanup, not task or application completion."""
        return self._retired

    @contextmanager
    def session(self) -> Iterator[CompletionReader]:
        """Require exact no-input capabilities before configuration and retire on every exit path."""
        try:
            reply = self._call("readonly_capabilities", {})
            _require_contract(reply)
            self._check()
            with operation_scope(TaskOperation(self._spec, self._check, self._parent.owner)):
                ready, reason = self._adapter.ready(self._spec)
            if not ready:
                raise AgentTaskError(reason or "completion reader is not ready")
            yield self
        finally:
            try:
                self._adapter.cleanup()
                self._retired = True
            finally:
                self._closed = True


def new_completion_target(source: NativeDesktopTarget) -> ReadOnlyNativeTarget:
    """Build an inert permanent read-only proxy, preserving only host-owned interpreter/profile/resource."""
    # pylint: disable-next=protected-access  # reason: trusted native-target collaborator checks the source's ownership
    if source._resource is not None or source._channel is not None or not source._ledger.empty or source._pending:
        raise AgentTaskError("source input must retire before a fresh completion reader")
    if not source.supports_readonly_completion:
        raise AgentTaskError("this target has no declared read-only completion helper")
    if source.is_managed_browser:
        raise AgentTaskError("browser completion requires the runtime's actual retained effect context")
    # pylint: disable-next=protected-access  # reason: copy host-owned interpreter selection, never task/model argv
    argv = source._argv[:-1] + ("je_auto_control.utils.agent_runtime.readonly_worker",)
    # pylint: disable-next=protected-access  # reason: retain the same physical resource and immutable host profile
    profile = source._profile.to_dict() if source._profile is not None else None
    # pylint: disable-next=protected-access  # reason: fresh read-only ownership must use the original resource lock/journal
    return ReadOnlyNativeTarget(argv=argv, resource_path=source._resource_path, profile=profile)


def open_completion_reader(source: NativeDesktopTarget, spec: AgentTaskSpec) -> Any:
    """Create a new helper only for the standard owned worker, preserving its host profile/resource."""
    return CompletionReader(new_completion_target(source), spec).session()
