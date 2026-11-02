"""Connection-local roots and live task ceilings retire with their owning MCP authority."""
from __future__ import annotations

import threading
from contextvars import copy_context
from typing import TYPE_CHECKING, Any, Callable

from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


class OriginPoliciesMixin:
    """Isolate client roots without changing the server's explicitly configured static policy."""

    if TYPE_CHECKING:
        _local: Any
        _notifier: Any
        _writer: Any
        _concurrent_tools: Any
        connection_scope: Callable[..., Any]
        _refresh_roots_safely: Callable[[], None]
        def _session_tool_view(self, *, stateless: bool | None = None) -> Any:
            """Obtain the host's accepted availability view."""

        @property
        def _connection_id(self) -> Any:
            """The host's active transport identity."""

    def _init_origin_policies(self) -> None:
        self._origin_policy_lock = threading.RLock()
        self._origin_policy_entries: dict[Any, ArgumentPolicy] = {}
        self._base_argument_policy: ArgumentPolicy | None = None

    @property
    def argument_policy(self) -> ArgumentPolicy:
        """The host-configured policy; replacing it revokes previously issued task ceilings."""
        if self._base_argument_policy is None:
            raise AgentTaskError("MCP argument policy has not been initialized")
        return self._base_argument_policy

    @argument_policy.setter
    def argument_policy(self, policy: ArgumentPolicy) -> None:
        with self._origin_policy_lock:
            if self._base_argument_policy is not None and self._base_argument_policy is not policy:
                self._base_argument_policy.path_policy.revoke_managed_origin()
                for previous in self._origin_policy_entries.values():
                    previous.path_policy.revoke_managed_origin()
                self._origin_policy_entries.clear()
            self._base_argument_policy = policy

    @property
    def _active_argument_policy(self) -> ArgumentPolicy:
        captured = getattr(self._local, "dispatch_argument_policy", None)
        if captured is not None:
            return captured
        connection = self._connection_id
        base = self.argument_policy
        if connection is None or not base.path_policy.use_client_roots:
            return base
        with self._origin_policy_lock:
            if connection not in self._origin_policy_entries:
                self._origin_policy_entries[connection] = ArgumentPolicy(base.path_policy.fork_for_client(),
                                                                        base.env_allowlist)
            return self._origin_policy_entries[connection]

    def _forget_origin_policy(self, connection: Any) -> None:
        with self._origin_policy_lock:
            policy = self._origin_policy_entries.pop(connection, None)
            if policy is not None:
                policy.path_policy.revoke_managed_origin()

    def _close_client_origin_policies(self) -> None:
        with self._origin_policy_lock:
            for policy in self._origin_policy_entries.values():
                policy.path_policy.revoke_managed_origin()
            self._origin_policy_entries.clear()
            if self.argument_policy.path_policy.use_client_roots:
                self.argument_policy.path_policy.revoke_managed_origin()

    def _root_refresh_worker(self) -> Callable[[], None]:
        context = copy_context()
        policy = self._active_argument_policy
        scope = {"notifier": self._notifier, "writer": self._writer,
                 "concurrent_tools": self._concurrent_tools, "connection_id": self._connection_id}

        def refresh() -> None:
            with self.connection_scope(**scope):
                self._local.root_refresh_policy = policy
                try:
                    self._refresh_roots_safely()
                finally:
                    del self._local.root_refresh_policy

        return lambda: context.run(refresh)

    def _capture_tool_worker(self, callback: Callable[[], None], *, view: Any = None) -> Callable[[], None]:
        """Retain accepted authority and exact session policy/view across a fresh worker thread."""
        context = copy_context()
        policy = self._active_argument_policy
        view = view if view is not None else self._session_tool_view()
        scope = {"notifier": self._notifier, "writer": self._writer,
                 "concurrent_tools": self._concurrent_tools, "connection_id": self._connection_id}

        def run() -> None:
            prior = (getattr(self._local, "dispatch_argument_policy", None),
                     getattr(self._local, "accepted_tool_view", None))
            with self.connection_scope(**scope):
                self._local.dispatch_argument_policy, self._local.accepted_tool_view = policy, view
                try:
                    callback()
                finally:
                    self._local.dispatch_argument_policy, self._local.accepted_tool_view = prior

        return lambda: context.run(run)
