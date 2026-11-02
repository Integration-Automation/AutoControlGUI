"""Explicit self-healing requests with optional post-click VLM verification."""
from typing import Any, Optional

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, MCPTool, MCPToolResult, schema


def _run(request: dict[str, Any], *, ctx: Optional[ToolCallContext] = None) -> MCPToolResult:
    # pylint: disable-next=import-outside-toplevel  # reason: keep runtime business imports out of registry initialization
    from je_auto_control.utils.self_healing.commands import run_json_request
    count = 0

    def progress(phase: str) -> None:
        nonlocal count
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(count, message=phase)
            count += 1
            ctx.check_cancelled()

    result = run_json_request(request, path_policy=ctx.path_policy if ctx is not None else None, observer=progress)
    failed = result.get("verified") is False
    return MCPToolResult(result, is_error=failed,
                         error_text="self-healing verification failed" if failed else None)


def healing_run_tools() -> list[MCPTool]:
    """Expose one JSON request without enabling verification implicitly."""
    # pylint: disable-next=import-outside-toplevel  # reason: schema construction runs after the facade is initialized
    from je_auto_control.utils.self_healing.commands import request_json_schema
    return [MCPTool(
        name="ac_self_heal_run",
        description=("Run an explicit locate/click request. Default operation is locate. "
                     "Optional verification.description opts into a fresh post-click configured-VLM check "
                     "which may incur API cost. False verification returns structured isError; "
                     "found and issued do not imply verified. Nested templates honor current path roots."),
        input_schema=schema({"request": request_json_schema()}, required=["request"]),
        handler=_run, annotations=DESTRUCTIVE,
    )]
