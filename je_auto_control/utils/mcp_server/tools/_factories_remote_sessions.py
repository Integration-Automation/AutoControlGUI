"""Named WebSocket/WebRTC transport and owned lifecycle tools."""

from functools import partial
from typing import Any, List

from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, READ_ONLY, MCPTool, schema


def _call(command: str, **arguments: Any) -> Any:
    # Lazy shared executor adapter; the MCP dispatcher enforces capability/path limits.
    # pylint: disable=import-outside-toplevel  # reason: lazy optional/cyclic boundary
    from je_auto_control.utils.executor.action_executor import executor
    # pylint: enable=import-outside-toplevel

    return executor.event_dict[command](**arguments)


def remote_session_tools() -> List[MCPTool]:
    """Expose named resources while preserving independent script transport defaults."""
    return [
        MCPTool(
            "ac_start_ws_host",
            "Remote Desktop: start_ws_host; optional session identity.",
            schema(
                {
                    "token": {"type": "string", "writeOnly": True},
                    "bind": {"type": "string"},
                    "port": {"type": "integer"},
                    "fps": {"type": "number"},
                    "quality": {"type": "integer"},
                    "region": {"type": "array"},
                    "max_clients": {"type": "integer"},
                    "session_id": {"type": "string"},
                },
                required=["token"],
            ),
            partial(_call, "AC_start_ws_host"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_stop_ws_host",
            "Remote Desktop: stop_ws_host; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_stop_ws_host"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_ws_host_status",
            "Remote Desktop: ws_host_status; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_ws_host_status"),
            READ_ONLY,
        ),
        MCPTool(
            "ac_ws_connect",
            "Remote Desktop: ws_connect; optional session identity.",
            schema(
                {
                    "host": {"type": "string"},
                    "port": {"type": "integer"},
                    "token": {"type": "string", "writeOnly": True},
                    "path": {"type": "string"},
                    "timeout": {"type": "number"},
                    "session_id": {"type": "string"},
                },
                required=["host", "port", "token"],
            ),
            partial(_call, "AC_ws_connect"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_ws_disconnect",
            "Remote Desktop: ws_disconnect; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_ws_disconnect"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_ws_viewer_status",
            "Remote Desktop: ws_viewer_status; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_ws_viewer_status"),
            READ_ONLY,
        ),
        MCPTool(
            "ac_ws_send_input",
            "Remote Desktop: ws_send_input; optional session identity.",
            schema({"action": {"type": "object"}, "session_id": {"type": "string"}}, required=["action"]),
            partial(_call, "AC_ws_send_input"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_start_webrtc_host",
            "Remote Desktop: start_webrtc_host; optional session identity.",
            schema(
                {
                    "token": {"type": "string", "writeOnly": True},
                    "read_only": {"type": "boolean"},
                    "session_id": {"type": "string"},
                },
                required=["token"],
            ),
            partial(_call, "AC_start_webrtc_host"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_webrtc_create_offer",
            "Remote Desktop: webrtc_create_offer; optional session identity.",
            schema({"peer_label": {"type": "string"}, "session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_webrtc_create_offer"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_webrtc_accept_answer",
            "Remote Desktop: webrtc_accept_answer; optional session identity.",
            schema({"answer_sdp": {"type": "string"}, "session_id": {"type": "string"}}, required=["answer_sdp"]),
            partial(_call, "AC_webrtc_accept_answer"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_stop_webrtc_host",
            "Remote Desktop: stop_webrtc_host; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_stop_webrtc_host"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_webrtc_host_status",
            "Remote Desktop: webrtc_host_status; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_webrtc_host_status"),
            READ_ONLY,
        ),
        MCPTool(
            "ac_start_webrtc_viewer",
            "Remote Desktop: start_webrtc_viewer; optional session identity.",
            schema(
                {
                    "token": {"type": "string", "writeOnly": True},
                    "viewer_id": {"type": "string"},
                    "session_id": {"type": "string"},
                },
                required=["token"],
            ),
            partial(_call, "AC_start_webrtc_viewer"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_webrtc_process_offer",
            "Remote Desktop: webrtc_process_offer; optional session identity.",
            schema(
                {
                    "offer_sdp": {"type": "string"},
                    "expected_dtls_fingerprint": {"type": "string"},
                    "session_id": {"type": "string"},
                },
                required=["offer_sdp"],
            ),
            partial(_call, "AC_webrtc_process_offer"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_webrtc_send_input",
            "Remote Desktop: webrtc_send_input; optional session identity.",
            schema({"action": {"type": "object"}, "session_id": {"type": "string"}}, required=["action"]),
            partial(_call, "AC_webrtc_send_input"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_stop_webrtc_viewer",
            "Remote Desktop: stop_webrtc_viewer; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_stop_webrtc_viewer"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_webrtc_viewer_status",
            "Remote Desktop: webrtc_viewer_status; optional session identity.",
            schema({"session_id": {"type": "string"}}, required=[]),
            partial(_call, "AC_webrtc_viewer_status"),
            READ_ONLY,
        ),
        MCPTool(
            "ac_remote_disconnect_session",
            "Remote Desktop: remote_disconnect_session; optional session identity.",
            schema({"session_id": {"type": "string"}, "owner": {"type": "string"}}, required=["session_id"]),
            partial(_call, "AC_remote_disconnect_session"),
            DESTRUCTIVE,
        ),
        MCPTool(
            "ac_remote_session_status",
            "Remote Desktop: remote_session_status; optional session identity.",
            schema({"session_id": {"type": "string"}, "owner": {"type": "string"}}, required=["session_id"]),
            partial(_call, "AC_remote_session_status"),
            READ_ONLY,
        ),
        MCPTool(
            "ac_remote_session_events",
            "Remote Desktop: remote_session_events; optional session identity.",
            schema({"owner": {"type": "string"}}, required=[]),
            partial(_call, "AC_remote_session_events"),
            READ_ONLY,
        ),
    ]
