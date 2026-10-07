"""Bind accepted MCP transport identity and policy to concurrent tool workers."""
from __future__ import annotations

import contextvars
import threading
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

if TYPE_CHECKING:
    from je_auto_control.utils.mcp_server.server import MCPServer


# pylint: disable=protected-access  # reason: this worker helper owns MCPServer internal dispatch state
def dispatch_tool_call_async(server: MCPServer, msg_id: Any, params: dict[str, Any]) -> None:
    """Retain the accepted peer, roots, capabilities and exact ContextVar view lease."""
    writer = server._writer
    binding = {'writer': writer, 'notifier': server._notifier, 'connection_id': server._connection_id,
               'concurrent_tools': False, 'accepted_path_policy': server._current_path_policy(),
               'accepted_capabilities': deepcopy(server._client_capabilities)}

    def worker() -> None:
        for name, value in binding.items():
            setattr(server._local, name, value)
        try:
            payload = server._build_response(msg_id, 'tools/call', params)
            if payload is None:
                return
            if writer is None:
                autocontrol_logger.warning('MCP async tool reply with no writer; dropping %s', msg_id)
                return
            writer(payload)
        finally:
            for name in binding:
                delattr(server._local, name)

    context = contextvars.copy_context()
    thread = threading.Thread(target=context.run, args=(worker,), daemon=True, name=f'MCPCall-{msg_id}')
    with server._workers_lock:
        server._workers = [live for live in server._workers if live.is_alive()]
        server._workers.append(thread)
    thread.start()

# pylint: enable=protected-access
