"""Record and replay HTTP interactions for deterministic, offline API tests.

The HTTP client hardcoded its ``urllib`` transport, so a flow that drives an
API could not be re-run without the live server. The client now exposes a
``build_call`` / ``urllib_transport`` seam; this module layers a VCR-style
cassette on top: **replay** returns a recorded response for a matching request
(pure, no network — the CI-valuable half), while **recording** is a thin
pass-through over a live transport.

Pure standard library (``json``); imports no ``PySide6``.
"""
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from je_auto_control.utils.exception.exceptions import AutoControlException

Transport = Callable[[Mapping[str, Any]], Dict[str, Any]]


class CassetteMissError(AutoControlException):
    """No recorded interaction matched the request during replay."""


def _decode_body(body: Any) -> Optional[str]:
    if body is None:
        return None
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _request_view(call: Mapping[str, Any]) -> Dict[str, Any]:
    return {"method": str(call.get("method", "GET")).upper(),
            "url": call.get("url"),
            "headers": dict(call.get("headers") or {}),
            "body": _decode_body(call.get("body"))}


def _matches(recorded: Mapping[str, Any], call: Mapping[str, Any],
             match_on: Sequence[str]) -> bool:
    view = _request_view(call)
    for field in match_on:
        if field == "method":
            if recorded.get("method") != view["method"]:
                return False
        elif field == "url":
            if recorded.get("url") != view["url"]:
                return False
        elif field == "body":
            if recorded.get("body") != view["body"]:
                return False
    return True


class Cassette:
    """A set of recorded request/response interactions (VCR-style)."""

    def __init__(self,
                 interactions: Optional[Sequence[Mapping[str, Any]]] = None) -> None:
        self._interactions: List[Dict[str, Any]] = [
            dict(item) for item in (interactions or [])]

    @property
    def interactions(self) -> List[Dict[str, Any]]:
        """The recorded interactions."""
        return self._interactions

    @classmethod
    def load(cls, path: str) -> "Cassette":
        """Load a cassette from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data.get("interactions", []))

    def save(self, path: str) -> str:
        """Write the cassette to ``path`` as JSON; return the path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"version": 1, "interactions": self._interactions}, indent=2),
            encoding="utf-8")
        return str(out)

    def record(self, call: Mapping[str, Any],
               response: Mapping[str, Any]) -> None:
        """Append one request/response interaction."""
        self._interactions.append({"request": _request_view(call),
                                   "response": dict(response)})

    def replay(self, call: Mapping[str, Any], *,
               match_on: Sequence[str] = ("method", "url")) -> Dict[str, Any]:
        """Return the recorded response for a matching ``call`` (no network)."""
        for interaction in self._interactions:
            if _matches(interaction.get("request", {}), call, match_on):
                return dict(interaction["response"])
        raise CassetteMissError(
            f"no recorded interaction for {call.get('method')} {call.get('url')}")

    def replay_transport(self, *,
                         match_on: Sequence[str] = ("method", "url")) -> Transport:
        """Return a transport that replays from this cassette."""
        return lambda call: self.replay(call, match_on=match_on)

    def recording_transport(self, inner: Transport) -> Transport:
        """Return a transport that records ``inner``'s live responses."""
        def transport(call: Mapping[str, Any]) -> Dict[str, Any]:
            response = inner(call)
            self.record(call, response)
            return response
        return transport
