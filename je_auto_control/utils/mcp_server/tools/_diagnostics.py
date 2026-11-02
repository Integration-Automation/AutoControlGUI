"""Explicit active diagnostic observations with per-request cancellation and progress."""
from functools import partial
from typing import Optional

from je_auto_control.utils.diagnostics.diagnostics import run_diagnostics
from je_auto_control.utils.exception.cancellation import CancellationToken, TaskProgress, cancellation_scope
from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema


def _progress(ctx: ToolCallContext, value: TaskProgress) -> None:
    ctx.progress(value.completed, value.total, 'Diagnostic checks completed')


class _DiagnosticToken(CancellationToken):
    def __init__(self, ctx: ToolCallContext) -> None:
        super().__init__(0, partial(_progress, ctx), event=ctx.cancelled_event)
        self._ctx = ctx

    def checkpoint(self) -> None:
        """Keep the established MCP request cancellation type and request identity."""
        self._ctx.check_cancelled()
        super().checkpoint()


def _diagnose(*, ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    if ctx is None:
        return run_diagnostics().to_dict()
    if not isinstance(ctx, ToolCallContext):
        raise TypeError('diagnostic context must be the server-owned ToolCallContext')
    with cancellation_scope(_DiagnosticToken(ctx)):
        return run_diagnostics().to_dict()


def diagnostic_tools() -> list[MCPTool]:
    """Expose the existing active SDK/AC report; capture may request consent and is never automatic."""
    check = schema({'name': {'type': 'string'}, 'ok': {'type': 'boolean'},
                    'severity': {'type': 'string', 'enum': ['info', 'warn', 'error']},
                    'detail': {'type': 'string'}, 'extra': {'type': 'object'}},
                   required=['name', 'ok', 'severity', 'detail', 'extra'])
    output = schema({'ok': {'type': 'boolean'}, 'count': {'type': 'integer', 'minimum': 0},
                     'failed': {'type': 'integer', 'minimum': 0}, 'checks': {'type': 'array', 'items': check}},
                    required=['ok', 'count', 'failed', 'checks'])
    return [MCPTool(
        name='ac_diagnose',
        description=('Explicitly run active system diagnostics, including screen capture which may request consent. '
                     'Reports check progress and observes this request cancellation in supported waits. '
                     'Use ac_probe_capabilities for passive metadata without capture or permission requests.'),
        input_schema={'type': 'object', 'properties': {}, 'additionalProperties': False},
        output_schema=output, handler=_diagnose, annotations=READ_ONLY,
    )]
