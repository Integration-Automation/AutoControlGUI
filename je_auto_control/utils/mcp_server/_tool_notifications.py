"""Publish tool-list changes to the live HTTP session streams owned by one transport."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._protocol import _notification_message
from je_auto_control.utils.mcp_server._subscriptions import _ALL_TOOL_CONNECTIONS

if TYPE_CHECKING:
    from je_auto_control.utils.mcp_server.server import MCPServer
    from je_auto_control.utils.mcp_server.http_sessions import SessionRegistry


class HTTPToolNotifications:
    """Register one detachable transport sink; stream lookup remains live through reconnects."""

    def __init__(self, owner: MCPServer, sessions: SessionRegistry) -> None:
        self._owner, self._sessions = owner, sessions
        self._closed = threading.Event()
        owner._register_tool_change_sink(self, self.notify)

    def notify(self, connection: Any) -> set[Any]:
        """Send once to each matching stream, returning identities already handled by this sink."""
        delivered: set[Any] = set()
        if self._closed.is_set():
            return delivered
        payload = _notification_message("notifications/tools/list_changed", {})
        for session, writer in self._sessions.stream_writers():
            if connection is not _ALL_TOOL_CONNECTIONS and connection != session:
                continue
            delivered.add(session)
            try:
                writer(payload)
            except (OSError, RuntimeError, ValueError) as error:
                autocontrol_logger.info("MCP session tool notification ended: %r", error)
        return delivered

    def close(self) -> None:
        """Retire the sink before its transport releases sockets and session state."""
        self._closed.set()
        # pylint: disable-next=protected-access  # reason: this owned transport sink must detach its private hook
        self._owner._unregister_tool_change_sink(self)
