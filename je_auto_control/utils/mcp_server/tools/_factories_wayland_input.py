"""Explicit raw physical recording and owned portal stop MCP commands."""
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, SIDE_EFFECT_ONLY, schema
from je_auto_control.wrapper.wayland_input import (
    start_physical_recording, stop_physical_recording, start_wayland_stop_shortcut,
    stop_wayland_stop_shortcut, wayland_input_status,
)


def wayland_input_tools() -> list[MCPTool]:
    """Expose explicit registration, raw event capture and passive lifecycle evidence."""
    return [
        MCPTool('ac_start_physical_recording',
                'Explicitly read selected physical Linux event nodes using existing ACLs; excludes virtual sources.',
                schema({'devices': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 16}},
                       required=['devices']), start_physical_recording, SIDE_EFFECT_ONLY),
        MCPTool('ac_stop_physical_recording',
                'Release the script recorder and return raw device units, not desktop coordinates or replay actions.',
                schema({}), stop_physical_recording, SIDE_EFFECT_ONLY),
        MCPTool('ac_start_wayland_stop_shortcut',
                'Explicitly request portal consent for a script stop binding; the compositor may change the trigger.',
                schema({'preferred_trigger': {'type': 'string', 'maxLength': 128}}),
                start_wayland_stop_shortcut, SIDE_EFFECT_ONLY),
        MCPTool('ac_stop_wayland_stop_shortcut', 'Cancel or close only the script-owned stop grant.',
                schema({}), stop_wayland_stop_shortcut, SIDE_EFFECT_ONLY),
        MCPTool('ac_wayland_input_status', 'Read local recording/stop evidence without I/O or consent.',
                schema({}), wayland_input_status, READ_ONLY),
    ]
