"""Failure-record data class shared by every ticket backend."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FailureReport:
    """One failed automation run that we want to file a ticket for."""

    source: str        # "scheduler" | "trigger" | "hotkey" | "rest" | ...
    source_id: str     # job_id / trigger_id / etc.
    script_path: Optional[str] = None
    error_text: str = ""
    log_tail: str = ""
    screenshot_path: Optional[str] = None
    timestamp_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(
            timespec="seconds",
        ),
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def render_summary(self) -> str:
        """Compact one-line summary suitable for a ticket title."""
        sid = self.source_id or "?"
        first_line = self.error_text.splitlines()[0] if self.error_text else "failure"
        return f"[AutoControl] {self.source}:{sid} — {first_line[:90]}"

    def render_body(self) -> str:
        """Markdown body for the ticket description."""
        parts = [
            f"**Source**: `{self.source}` / `{self.source_id}`",
            f"**Time**: {self.timestamp_iso}",
        ]
        if self.script_path:
            parts.append(f"**Script**: `{self.script_path}`")
        if self.screenshot_path:
            parts.append(f"**Screenshot**: `{self.screenshot_path}`")
        if self.error_text:
            parts.append("\n**Error**:\n```\n" + self.error_text + "\n```")
        if self.log_tail:
            parts.append("\n**Log tail**:\n```\n" + self.log_tail + "\n```")
        if self.metadata:
            parts.append("\n**Metadata**:")
            for key, value in sorted(self.metadata.items()):
                parts.append(f"- `{key}`: `{value}`")
        return "\n".join(parts)


@dataclass(frozen=True)
class TicketResult:
    """Outcome of one backend's attempt to file a ticket."""

    backend: str
    succeeded: bool
    ticket_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


__all__ = ["FailureReport", "TicketResult"]
