"""Bridge Python logging records onto MCP ``notifications/message``.

Once attached to the project logger, every record at or above the
configured level is forwarded to the MCP client as a notification so
the client can mirror server-side activity in its UI. The handler is
no-op when the server's notifier is not yet connected — useful for
unit tests that don't actually start a transport.
"""
import logging
from typing import Any, Callable, Dict, Optional

# MCP log levels (RFC 5424 syslog names) mapped from stdlib logging levels.
_LEVEL_NAME_FROM_LEVEL = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warning",
    logging.ERROR: "error",
    logging.CRITICAL: "critical",
}

_LEVEL_FROM_MCP_NAME = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


def mcp_level_to_logging(name: str) -> Optional[int]:
    """Return the :mod:`logging` level for an MCP log name, or ``None``."""
    return _LEVEL_FROM_MCP_NAME.get(str(name).strip().lower())


def logging_level_to_mcp(level: int) -> str:
    """Return the closest MCP level name for a stdlib logging level."""
    closest = max(
        (lvl for lvl in _LEVEL_NAME_FROM_LEVEL if lvl <= int(level)),
        default=logging.DEBUG,
    )
    return _LEVEL_NAME_FROM_LEVEL[closest]


class MCPLogBridge(logging.Handler):
    """Logging handler that forwards records as ``notifications/message``."""

    def __init__(self, notifier: Optional[
            Callable[[str, Dict[str, Any]], None]] = None,
                 logger_name: str = "je_auto_control",
                 level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._notifier = notifier
        self._logger_name = str(logger_name)

    def set_notifier(self, notifier: Optional[
            Callable[[str, Dict[str, Any]], None]]) -> None:
        self._notifier = notifier

    def emit(self, record: logging.LogRecord) -> None:
        notifier = self._notifier
        if notifier is None:
            return
        try:
            text = record.getMessage()
        except (TypeError, ValueError):
            text = str(record.msg)
        params: Dict[str, Any] = {
            "level": logging_level_to_mcp(record.levelno),
            "logger": self._logger_name,
            "data": {
                "logger": record.name,
                "message": text,
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
            },
        }
        try:
            notifier("notifications/message", params)
        except (OSError, RuntimeError, ValueError):
            # The bridge must never crash the producer.
            pass


__all__ = [
    "MCPLogBridge", "logging_level_to_mcp", "mcp_level_to_logging",
]
