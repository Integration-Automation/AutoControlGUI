"""Emit automation events as CloudEvents (CNCF spec 1.0).

AutoControl can *receive* webhooks but had no way to *emit* events outbound.
CloudEvents 1.0 is the interop standard for event payloads (Knative, Azure Event
Grid, iPaaS, generic webhooks). This wraps run-lifecycle / assertion / failure
data in a CloudEvents envelope and (optionally) POSTs it over the HTTP binding,
reusing the framework's egress allowlist guard.

The transport is injectable (a ``sink`` callable), so emission is unit-testable
with no network. Pure standard library; imports no ``PySide6``.
"""
import datetime
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional

SPEC_VERSION = "1.0"


def to_cloudevent(event_type: str, source: str, data: Any, *,
                  subject: Optional[str] = None,
                  event_id: Optional[str] = None,
                  time: Optional[str] = None) -> Dict[str, Any]:
    """Wrap ``data`` in a CloudEvents 1.0 (structured JSON) envelope."""
    envelope: Dict[str, Any] = {
        "specversion": SPEC_VERSION,
        "id": event_id or uuid.uuid4().hex,
        "source": source,
        "type": event_type,
        "time": time or datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "data": data,
    }
    if subject is not None:
        envelope["subject"] = subject
    return envelope


def post_cloudevent(url: str, event: Mapping[str, Any], *,
                    timeout: float = 10.0,
                    poster: Optional[Callable[..., Any]] = None) -> int:
    """POST a CloudEvent to ``url`` (structured mode); return the status code.

    Uses the framework's egress-guarded HTTP client by default; pass ``poster``
    to inject a transport in tests.
    """
    if poster is not None:
        return int(poster(url, event))
    from je_auto_control.utils.http_client.http_client import http_request
    headers = {"Content-Type": "application/cloudevents+json"}
    response = http_request(url, method="POST", json_body=dict(event),
                            headers=headers, timeout=timeout)
    return int(response.get("status", 0))


class EventEmitter:
    """Builds CloudEvents from a fixed source and dispatches them to a sink."""

    def __init__(self, sink: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 *, source: str = "je_auto_control") -> None:
        """``sink(event)`` receives each envelope; defaults to an in-memory log."""
        self._source = source
        self._log: List[Dict[str, Any]] = []
        self._sink = sink if sink is not None else self._log.append

    def emit(self, event_type: str, data: Any, *,
             subject: Optional[str] = None) -> Dict[str, Any]:
        """Build a CloudEvent and hand it to the sink; return the envelope."""
        event = to_cloudevent(event_type, self._source, data, subject=subject)
        self._sink(event)
        return event

    @property
    def events(self) -> List[Dict[str, Any]]:
        """Envelopes captured by the default in-memory sink."""
        return list(self._log)
