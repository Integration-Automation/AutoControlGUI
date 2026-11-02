"""Dependency-free cancellation carriers and interruption classification shared by transport and execution."""
from asyncio import CancelledError
from concurrent.futures import CancelledError as FutureCancelledError
from typing import Any, Optional


class OperationCancelledError(RuntimeError):
    """An MCP control signal, deliberately outside ordinary framework-error containment.

    The established mcp_server.context import remains an alias. RuntimeError-only
    ancestry is preserved so a cancellation crosses family handlers unchanged.
    """

    def __init__(self, request_id: Any) -> None:
        super().__init__(f"tool call {request_id!r} was cancelled by the client")
        self.request_id = request_id


def is_run_interruption(error: BaseException) -> bool:
    """Whether an error represents an explicit cancellation or hard control signal."""
    return isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit, CancelledError,
                              FutureCancelledError, OperationCancelledError))


def raise_if_run_interrupted(error: BaseException) -> None:
    """Keep cancellation out of ordinary failure recovery and retry boundaries."""
    if is_run_interruption(error):
        raise error


def raise_caused_run_interruption(error: BaseException) -> None:
    """Preserve explicit wrapped interruption identity, with bounded traversal of cyclic exception causes."""
    current: Optional[BaseException] = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if len(seen) >= 64:
            raise error
        seen.add(id(current))
        raise_if_run_interrupted(current)
        current = current.__cause__
