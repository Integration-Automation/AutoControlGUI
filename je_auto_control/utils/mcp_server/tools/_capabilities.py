"""Read-only MCP capability metadata; no native permission, capture or input operation is performed."""
from je_auto_control.utils.diagnostics.capability_commands import probe_current_capabilities
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema


def capability_tools() -> list[MCPTool]:
    """Expose the same passive snapshot as the SDK and AC_probe_capabilities."""
    fields = {
        'name': {'type': 'string', 'enum': ['input', 'capture']},
        'state': {'type': 'string', 'enum': ['available', 'unverified', 'needs_permission', 'needs_dependency',
                                          'unsupported', 'paused', 'revoked', 'failed']},
        'backend': {'type': 'string'}, 'reason': {'type': 'string'}, 'recovery': {'type': 'string'},
        'desktop_wide': {'type': 'boolean'},
    }
    status = schema(fields, required=list(fields))
    status['additionalProperties'] = False
    output = schema({'platform': {'type': 'string'}, 'display_server': {'type': 'string'},
                     'passive': {'type': 'boolean', 'const': True}, 'input': status, 'capture': status},
                    required=['platform', 'display_server', 'passive', 'input', 'capture'])
    output['additionalProperties'] = False
    return [MCPTool(
        name='ac_probe_capabilities',
        description=('Inspect key/pointer input and capture independently without loading native libraries, '
                     'connecting, requesting permission or operating the desktop. Dependencies do not prove readiness; '
                     'available means last local observation, which may be stale. XWayland is explicitly limited. '
                     'Every real operation still enforces current authority; this result grants none.'),
        input_schema={'type': 'object', 'properties': {}, 'additionalProperties': False},
        output_schema=output, handler=probe_current_capabilities, annotations=READ_ONLY,
    )]
