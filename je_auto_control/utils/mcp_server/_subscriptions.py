"""Change notifications of the MCP server: list changes and resource updates.

The handshake era subscribes to a resource with ``resources/subscribe`` and is
sent ``notifications/resources/updated`` and ``notifications/tools/list_changed``
on its connection's notifier, which is also where they go to a peer that never
subscribed to anything. Neither goes to a stateless peer
(``_unsolicited_notifier``).
"""
import functools
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._protocol import _MCPError


class SubscriptionMixin:
    """Subscription handlers, mixed into :class:`MCPServer`.

    Requires the host to provide ``_resources``, ``_resource_subscriptions``,
    ``_subscriptions_lock`` and ``_unsolicited_notifier``.
    """

    if TYPE_CHECKING:
        _resources: Any
        _resource_subscriptions: Dict[str, Any]
        _subscriptions_lock: threading.Lock

        def _unsolicited_notifier(self) -> Optional[Callable[[str, Dict[str, Any]], None]]:
            """The notifier for a notification no request asked for, or ``None``."""

    def _notify_tools_list_changed(self) -> None:
        notifier = self._unsolicited_notifier()
        if notifier is None:
            return
        try:
            notifier("notifications/tools/list_changed", {})
        except (OSError, RuntimeError, ValueError):
            autocontrol_logger.exception(
                "MCP failed to send tools/list_changed",
            )

    def _handle_resources_subscribe(self,
                                    params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise _MCPError(-32602, "resources/subscribe requires 'uri'")
        # Hold the lock across the check *and* the subscribe so two concurrent
        # requests for the same uri cannot both create a provider handle and
        # leak the loser (a TOCTOU that left an orphaned subscription running).
        with self._subscriptions_lock:
            if uri in self._resource_subscriptions:
                return {}
            handle = self._resources.subscribe(
                uri,
                functools.partial(self._notify_resource_updated, uri),
            )
            if handle is None:
                raise _MCPError(-32602, f"Unsubscribable resource: {uri}")
            self._resource_subscriptions[uri] = handle
        return {}

    def _handle_resources_unsubscribe(self,
                                      params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise _MCPError(-32602, "resources/unsubscribe requires 'uri'")
        with self._subscriptions_lock:
            handle = self._resource_subscriptions.pop(uri, None)
        if handle is not None:
            self._resources.unsubscribe(uri, handle)
        return {}

    def _notify_resource_updated(self, uri: str) -> None:
        notifier = self._unsolicited_notifier()
        if notifier is None:
            return
        try:
            notifier("notifications/resources/updated", {"uri": uri})
        except (OSError, RuntimeError, ValueError):
            autocontrol_logger.exception(
                "MCP failed to send resources/updated for %s", uri,
            )
