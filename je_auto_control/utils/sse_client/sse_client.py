"""Client-side Server-Sent Events (``text/event-stream``) parser.

The MCP HTTP transport *emits* SSE, but nothing consumed it: an LLM, agent, or
chatops endpoint that streams ``text/event-stream`` left ``http_request`` with a
raw, unparsed blob. This implements the WHATWG event-stream parsing algorithm —
``event`` / ``data`` / ``id`` / ``retry`` fields, comment lines, the leading
space rule, and blank-line dispatch — with incremental ``feed`` for chunks.

Pure standard library (``re``); imports no ``PySide6``. The parser is pure and
fully deterministic, so streaming logic is CI-testable without a live server.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

_LINE_SPLIT = re.compile(r"\r\n|\r|\n")


@dataclass(frozen=True)
class SSEEvent:
    """One dispatched Server-Sent Event."""

    event: str = "message"
    data: str = ""
    id: Optional[str] = None
    retry: Optional[int] = None

    def to_dict(self) -> dict:
        """Return a JSON-friendly view of the event."""
        return {"event": self.event, "data": self.data,
                "id": self.id, "retry": self.retry}


class SSEParser:
    """Incremental WHATWG ``text/event-stream`` parser."""

    def __init__(self) -> None:
        self._buffer = ""
        self._event = ""
        self._data: List[str] = []
        self._last_id: Optional[str] = None
        self._retry: Optional[int] = None

    def feed(self, chunk: str) -> List[SSEEvent]:
        """Feed a chunk of stream text; return any complete events."""
        lines = _LINE_SPLIT.split(self._buffer + chunk)
        self._buffer = lines.pop()          # trailing partial line
        events = [event for event in (self._process_line(line)
                                      for line in lines) if event is not None]
        return events

    def close(self) -> List[SSEEvent]:
        """Flush a trailing line and any pending event at end of stream."""
        events: List[SSEEvent] = []
        if self._buffer:
            trailing = self._process_line(self._buffer)
            self._buffer = ""
            if trailing is not None:
                events.append(trailing)
        final = self._dispatch()
        if final is not None:
            events.append(final)
        return events

    def _process_line(self, line: str) -> Optional[SSEEvent]:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        self._set_field(field, value)
        return None

    def _set_field(self, field: str, value: str) -> None:
        if field == "event":
            self._event = value
        elif field == "data":
            self._data.append(value)
        elif field == "id" and "\x00" not in value:
            self._last_id = value
        elif field == "retry" and value.isdigit():
            self._retry = int(value)

    def _dispatch(self) -> Optional[SSEEvent]:
        if not self._data:
            self._event = ""
            return None
        event = SSEEvent(event=self._event or "message",
                         data="\n".join(self._data),
                         id=self._last_id, retry=self._retry)
        self._event = ""
        self._data = []
        return event


def parse_event_stream(text: str) -> List[SSEEvent]:
    """Parse a complete ``text/event-stream`` blob into events.

    Flushes a trailing event even when the stream lacks a final blank line.
    """
    parser = SSEParser()
    events = parser.feed(text or "")
    events.extend(parser.close())
    return events
