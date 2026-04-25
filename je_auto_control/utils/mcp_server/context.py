"""Per-call context object passed to opt-in MCP tool handlers.

A handler that declares a ``ctx`` parameter receives a
:class:`ToolCallContext`, which lets it report progress to the
client and observe cooperative cancellation requests. Handlers that
do not declare ``ctx`` are unaffected.
"""
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class OperationCancelledError(RuntimeError):
    """Raised by :meth:`ToolCallContext.check_cancelled` when the client cancels."""

    def __init__(self, request_id: Any) -> None:
        super().__init__(f"tool call {request_id!r} was cancelled by the client")
        self.request_id = request_id


@dataclass
class ToolCallContext:
    """State threaded through one ``tools/call`` request.

    Handlers can call :meth:`progress` to push a
    ``notifications/progress`` to the client (no-op when the client
    did not provide a ``progressToken``), and check
    :attr:`cancelled` (or call :meth:`check_cancelled`) at safe
    points to abort cooperatively.
    """

    request_id: Any
    progress_token: Any = None
    notifier: Optional[Callable[[str, dict], None]] = field(
        default=None, repr=False,
    )
    cancelled_event: threading.Event = field(default_factory=threading.Event)

    @property
    def cancelled(self) -> bool:
        """``True`` once the client has sent ``notifications/cancelled``."""
        return self.cancelled_event.is_set()

    def check_cancelled(self) -> None:
        """Raise :class:`OperationCancelledError` if the call was cancelled."""
        if self.cancelled:
            raise OperationCancelledError(self.request_id)

    def progress(self, value: float, total: Optional[float] = None,
                 message: Optional[str] = None) -> None:
        """Send ``notifications/progress`` to the client.

        :param value: monotonic progress value (0..total when ``total`` is set,
            otherwise an arbitrary increasing scalar).
        :param total: optional upper bound for percent-style displays.
        :param message: optional human-readable status string.
        """
        if self.progress_token is None or self.notifier is None:
            return
        params: dict = {
            "progressToken": self.progress_token,
            "progress": float(value),
        }
        if total is not None:
            params["total"] = float(total)
        if message is not None:
            params["message"] = str(message)
        self.notifier("notifications/progress", params)


__all__ = ["OperationCancelledError", "ToolCallContext"]
