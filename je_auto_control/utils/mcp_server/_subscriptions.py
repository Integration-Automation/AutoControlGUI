"""Change notifications of the MCP server: list changes and resource updates.

The handshake era subscribes to a resource with ``resources/subscribe`` and is
sent ``notifications/resources/updated`` and ``notifications/tools/list_changed``
on its connection's notifier, which is also where they go to a peer that never
subscribed to anything. Neither goes to a stateless peer
(``_unsolicited_notifier``).

MCP 2026-07-28 replaces all of that with ``subscriptions/listen``: one
long-lived request per subscription, whose response stream carries only the
notification types the client asked for. The server acknowledges first
(``notifications/subscriptions/acknowledged``, listing the types it will send),
tags every notification with the request's id under
``io.modelcontextprotocol/subscriptionId``, and answers the request itself only
when it ends the subscription on its own initiative. The client ends it with
``notifications/cancelled`` (stdio) or by closing the stream (HTTP), and gets
no answer then.
"""
import functools
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._protocol import (
    _is_hashable, _MCPError, _notification_message, _result_response,
)
from je_auto_control.utils.mcp_server._stateless import LISTEN_METHOD, META_SUBSCRIPTION_ID

#: Returned by a handler whose request is answered later, or never.
NO_RESPONSE = object()
_ACKNOWLEDGED = "notifications/subscriptions/acknowledged"
_FILTER_FLAGS = ("toolsListChanged", "promptsListChanged", "resourcesListChanged")
_SEND_ERRORS = (OSError, RuntimeError, ValueError)


class Listener:
    """One open ``subscriptions/listen``: what it agreed to send, and where to."""

    def __init__(self, request_id: Any, emit: Callable[[str], None],
                 tools_list_changed: bool) -> None:
        self.request_id = request_id
        self.tools_list_changed = tools_list_changed
        self.resource_handles: Dict[str, Any] = {}
        #: Set when the subscription has ended, for whichever reason.
        self.closed = threading.Event()
        self._emit = emit
        self._lock = threading.Lock()
        self._acknowledged = False

    def _meta(self) -> Dict[str, Any]:
        return {META_SUBSCRIPTION_ID: self.request_id}

    def _write(self, line: str) -> bool:
        try:
            self._emit(line)
        except _SEND_ERRORS as error:
            autocontrol_logger.info("MCP subscription %r lost its stream: %r",
                                    self.request_id, error)
            return False
        return True

    def acknowledge(self, agreed: Dict[str, Any]) -> bool:
        """Send the acknowledgement; nothing on this subscription goes out before it."""
        with self._lock:
            self._acknowledged = self._write(_notification_message(
                _ACKNOWLEDGED, {"_meta": self._meta(), "notifications": agreed}))
            return self._acknowledged

    def notify(self, method: str, params: Dict[str, Any]) -> bool:
        """Send a change notification; ``False`` when the stream is gone."""
        with self._lock:
            if not self._acknowledged or self.closed.is_set():
                return True
            return self._write(_notification_message(method, {**params, "_meta": self._meta()}))

    def finish(self) -> None:
        """Answer the listen request: the subscription ended gracefully."""
        with self._lock:
            self._write(_result_response(
                self.request_id, {"resultType": "complete", "_meta": self._meta()}))


def _invalid(message: str) -> _MCPError:
    return _MCPError(-32602, f"Invalid params: {message}")


def _listen_filter(params: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """``(toolsListChanged, resource URIs)`` from a listen request's filter."""
    wanted = params.get("notifications")
    if not isinstance(wanted, dict):
        raise _invalid(f"{LISTEN_METHOD} needs a notifications object")
    for flag in _FILTER_FLAGS:
        if flag in wanted and not isinstance(wanted[flag], bool):
            raise _invalid(f"notifications.{flag} must be a boolean")
    uris = wanted.get("resourceSubscriptions", [])
    if not isinstance(uris, list) or not all(isinstance(uri, str) for uri in uris):
        raise _invalid("notifications.resourceSubscriptions must be a list of strings")
    return wanted.get("toolsListChanged") is True, list(dict.fromkeys(uris))


class SubscriptionMixin:
    """Subscription handlers, mixed into :class:`MCPServer`.

    Requires the host to provide ``_resources``, ``_resource_subscriptions``,
    ``_subscriptions_lock``, ``_listeners``, ``_listeners_lock``, ``_writer``,
    ``_connection_id`` and ``_unsolicited_notifier``.
    """

    if TYPE_CHECKING:
        _resources: Any
        _resource_subscriptions: Dict[str, Any]
        _subscriptions_lock: threading.Lock
        _listeners: Dict[Any, Listener]
        _listeners_lock: threading.Lock
        _writer: Optional[Callable[[str], None]]
        #: The notifier for a notification no request asked for, or ``None``.
        _unsolicited_notifier: Callable[[], Optional[Callable[[str, Dict[str, Any]], None]]]

        @property
        def _connection_id(self) -> Any:
            """Identity of the connection the current request arrived on."""

    def _notify_tools_list_changed(self) -> None:
        with self._listeners_lock:
            listening = [(key, listener) for key, listener in self._listeners.items()
                         if listener.tools_list_changed]
        for key, listener in listening:
            if not listener.notify("notifications/tools/list_changed", {}):
                self._end_listener(key, graceful=False)
        notifier = self._unsolicited_notifier()
        if notifier is None:
            return
        try:
            notifier("notifications/tools/list_changed", {})
        except (OSError, RuntimeError, ValueError):
            autocontrol_logger.exception(
                "MCP failed to send tools/list_changed",
            )

    # --- 2026-07-28: subscriptions/listen -------------------------------------

    def _listen(self, msg_id: Any, params: Dict[str, Any]) -> object:
        """Open a ``subscriptions/listen``: acknowledge now, answer when it ends."""
        writer = self._writer
        if writer is None:
            raise _MCPError(-32600, f"Invalid Request: {LISTEN_METHOD} needs a stream to notify on")
        if not _is_hashable(msg_id):
            raise _MCPError(-32600, "Invalid Request: id must be a string or a number")
        tools_list_changed, uris = _listen_filter(params)
        key = (self._connection_id, msg_id)
        listener = Listener(msg_id, writer, tools_list_changed)
        with self._listeners_lock:
            if key in self._listeners:
                raise _MCPError(-32600, f"Invalid Request: id {msg_id!r} is already listening")
            self._listeners[key] = listener
        agreed: Dict[str, Any] = {"toolsListChanged": True} if tools_list_changed else {}
        for uri in uris:
            handle = self._resources.subscribe(
                uri, functools.partial(self._listener_resource_updated, key, uri))
            if handle is not None:
                listener.resource_handles[uri] = handle
        if listener.resource_handles:
            agreed["resourceSubscriptions"] = list(listener.resource_handles)
        if not listener.acknowledge(agreed):
            self._end_listener(key, graceful=False)
        return NO_RESPONSE

    def _listener_resource_updated(self, key: Any, uri: str) -> None:
        with self._listeners_lock:
            listener = self._listeners.get(key)
        if listener is not None and not listener.notify(
                "notifications/resources/updated", {"uri": uri}):
            self._end_listener(key, graceful=False)

    def _end_listener(self, key: Any, graceful: bool) -> bool:
        """End one subscription; ``graceful`` answers its listen request first."""
        with self._listeners_lock:
            listener = self._listeners.pop(key, None)
        if listener is None:
            return False
        for uri, handle in listener.resource_handles.items():
            self._resources.unsubscribe(uri, handle)
        if graceful:
            listener.finish()
        listener.closed.set()
        return True

    def _end_listeners(self, which: Callable[[Any], bool], graceful: bool) -> None:
        """End every subscription whose connection id satisfies ``which``."""
        with self._listeners_lock:
            keys = [key for key in self._listeners if which(key[0])]
        for key in keys:
            self._end_listener(key, graceful)

    def end_subscriptions(self, *, stdio: bool, graceful: bool = True) -> None:
        """End the stdio peer's subscriptions, or every HTTP connection's.

        Called when that transport shuts down; ``graceful`` answers each
        listen request with a completion result first, as the specification
        asks of a server that ends a subscription on its own initiative.
        """
        self._end_listeners(lambda conn: (conn is None) == stdio, graceful)

    def subscription(self, connection_id: Any, request_id: Any) -> Optional[threading.Event]:
        """The event set when that subscription ends; ``None`` when it is not open."""
        with self._listeners_lock:
            listener = self._listeners.get((connection_id, request_id))
        return listener.closed if listener is not None else None

    def end_subscription(self, connection_id: Any, request_id: Any) -> None:
        """End a subscription whose client went away; nothing is sent."""
        self._end_listener((connection_id, request_id), graceful=False)

    # --- handshake era: resources/subscribe ------------------------------------

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
