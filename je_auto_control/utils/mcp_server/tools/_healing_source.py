"""Read-only original journal-step inspection from self-healing provenance."""
from typing import Optional

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema


def _source(path: str, run_id: str, step_id: str, limit: int = 100, *,
              ctx: Optional[ToolCallContext] = None) -> list[dict[str, object]]:
    # pylint: disable-next=import-outside-toplevel  # reason: keep business imports out of registry initialization
    from je_auto_control.utils.self_healing.source_inspection import inspect_heal_source

    def progress(count: int) -> None:
        if ctx is not None:
            ctx.check_cancelled()
            ctx.progress(count, message="source journal scan")
            ctx.check_cancelled()

    progress(0)
    result = inspect_heal_source(path, run_id, step_id, limit=limit, observer=progress,
                                  path_policy=ctx.path_policy if ctx is not None else None)
    if ctx is not None:
        ctx.check_cancelled()
    return result


def healing_source_tools() -> list[MCPTool]:
    """Expose bounded source inspection without replaying any recorded command."""
    return [MCPTool(
        name="ac_self_heal_source",
        description=("Inspect the original journal step using journal_path as path, run_id and step_id "
                     "from a captured self-healing record. Returns sanitized lifecycle snapshots only; "
                     "no capture, input or replay. Legacy/uncaptured rows have no journal path. "
                     "Current roots and cancellation apply; filtering precedes limit."),
        input_schema=schema({"path": {"type": "string", "format": "path"},
                             "run_id": {"type": "string", "minLength": 1},
                             "step_id": {"type": "string", "minLength": 1},
                             "limit": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 100}},
                            required=["path", "run_id", "step_id"]),
        handler=_source, annotations=READ_ONLY,
    )]
