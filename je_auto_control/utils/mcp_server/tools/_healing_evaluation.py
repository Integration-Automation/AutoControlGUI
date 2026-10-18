"""Read-only local locator comparisons with bounded file access and cancellation."""
from typing import Optional

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema


def _evaluate(path: str, *, ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    # pylint: disable-next=import-outside-toplevel  # reason: defer evaluator business imports until tool execution
    from je_auto_control.utils.self_healing.evaluation_io import evaluate_healing_manifest

    previous = -1

    def progress(count: int) -> None:
        nonlocal previous
        if ctx is not None:
            ctx.check_cancelled()
            if count != previous:
                ctx.progress(count, message="Locator comparisons completed")
                previous = count
            ctx.check_cancelled()

    result = evaluate_healing_manifest(path, path_policy=ctx.path_policy if ctx is not None else None,
                                       observer=progress)
    return result.to_dict()


def healing_evaluation_tools() -> list[MCPTool]:
    """Expose the same experimental report as API, executor and GUI."""
    return [MCPTool(
        name="ac_self_heal_evaluate",
        description=("Compare local image locator versions on fixed PNG samples from a schema-v1 manifest. "
                     "Returns labelled accuracy, false positives, verified recovery and latency populations. "
                     "Never captures, clicks or selects a network backend. Private file reads need drive_input."),
        input_schema=schema({"path": {"type": "string", "format": "path"}}, required=["path"]),
        handler=_evaluate, annotations=READ_ONLY,
        output_schema=schema({"schema_version": {"type": "integer"}, "cost_unit": {"type": "string"},
                              "versions": {"type": "object"}, "attempts": {"type": "array"}},
                             required=["schema_version", "cost_unit", "versions", "attempts"]),
    )]
