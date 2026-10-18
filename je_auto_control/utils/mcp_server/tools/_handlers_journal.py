"""MCP journal operations with durable progress and cooperative cancellation."""
import threading
from typing import Any, Optional

from je_auto_control.utils.mcp_server.context import ToolCallContext
from je_auto_control.utils.mcp_server.tools._base import MCPToolResult


class _CallProgress:
    """Serialize completed-step notifications from joined local workers."""

    def __init__(self, ctx: ToolCallContext) -> None:
        self.ctx = ctx
        self.value = 0
        self._lock = threading.Lock()

    def __call__(self, status: str) -> None:
        self.ctx.check_cancelled()
        if status == "incomplete":
            return
        with self._lock:
            self.value += 1
            self.ctx.progress(self.value, message="Journal steps completed")

    def scanned(self, count: int) -> None:
        """Check each record; coalesce read progress notifications in batches."""
        self.ctx.check_cancelled()
        self.value = count
        if count % 100 == 0:
            self.ctx.progress(count, message="Journal snapshots validated")


def journal_capture(actions: list[Any], path: str, metadata: Optional[dict[str, str]] = None,
                     variables: Optional[dict[str, object]] = None, dry_run: bool = False, *,
                     ctx: Optional[ToolCallContext] = None) -> MCPToolResult:
    """Capture an isolated run, retaining result metadata on recorded failures."""
    # pylint: disable-next=import-outside-toplevel  # reason: keep journal business imports lazy in the tool registry
    from je_auto_control.utils.action_journal.run import JournalRunOptions, execute_journal_run
    progress = _start(ctx, "Capturing actions")
    labels = metadata if metadata is not None else {}
    result = execute_journal_run(actions, path, options=JournalRunOptions(
        variables=variables, dry_run=dry_run, run_id=labels.get("run_id"), device_id=labels.get("device_id"),
        session_id=labels.get("session_id"), observer=progress,
        path_policy=ctx.path_policy if ctx is not None else None))
    _finished(progress, "Journal capture finished")
    failures = result["failed_actions"]
    return MCPToolResult(result, is_error=failures > 0,
                         error_text=f"{failures} action(s) failed" if failures else None)


def journal_read(path: str, run_id: Optional[str] = None, limit: int = 100, *,
                  ctx: Optional[ToolCallContext] = None) -> dict[str, object]:
    """Inspect sanitized snapshots while allowing cancellation during validation."""
    # pylint: disable-next=import-outside-toplevel  # reason: keep journal business imports lazy in the tool registry
    from je_auto_control.utils.action_journal.inspection import inspect_journal
    progress = _start(ctx, "Reading journal")
    events = inspect_journal(path, run_id=run_id, limit=limit,
                             observer=progress.scanned if progress is not None else None,
                             path_policy=ctx.path_policy if ctx is not None else None)
    _finished(progress, "Journal read finished")
    return {"events": events}


def _start(ctx: Optional[ToolCallContext], message: str) -> Optional[_CallProgress]:
    if ctx is None:
        return None
    ctx.check_cancelled()
    ctx.progress(0, message=message)
    return _CallProgress(ctx)


def _finished(progress: Optional[_CallProgress], message: str) -> None:
    if progress is not None:
        progress.ctx.check_cancelled()
        progress.ctx.progress(progress.value, message=message)
