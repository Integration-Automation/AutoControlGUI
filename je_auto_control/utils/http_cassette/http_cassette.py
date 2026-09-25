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
from je_auto_control.utils.executor.action_redaction import SENSITIVE_ARGUMENT_NAMES
from je_auto_control.utils.http_headers import CREDENTIAL_HEADERS

Transport = Callable[[Mapping[str, Any]], Dict[str, Any]]


class CassetteMissError(AutoControlException):
    """No recorded interaction matched the request during replay."""


def _decode_body(body: Any) -> Optional[str]:
    if body is None:
        return None
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


#: Headers whose values are credentials: never written to a cassette.
SENSITIVE_HEADERS = CREDENTIAL_HEADERS
REDACTED = "<redacted>"
_MATCH_FIELDS = ("method", "url", "body", "headers")


def _redacted(headers: Any) -> Dict[str, Any]:
    """``headers`` with credential values replaced by :data:`REDACTED`."""
    return {name: REDACTED if str(name).lower() in SENSITIVE_HEADERS else value
            for name, value in dict(headers or {}).items()}


#: Query parameters that carry a credential ("key" is an API key in a URL).
_SENSITIVE_QUERY = SENSITIVE_ARGUMENT_NAMES | {"key", "apikey", "sig", "signature"}


def _request_view(call: Mapping[str, Any]) -> Dict[str, Any]:
    """The request as recorded: credentials masked in headers, query and body.

    Only headers were masked, so a query-string key, a password in a JSON
    body and a token in the response went into the saved file. A live call
    is matched against its own view, so masked fields still match.
    """
    return {"method": str(call.get("method", "GET")).upper(),
            "url": _redacted_url(call.get("url")),
            "headers": _redacted(call.get("headers")),
            "body": _redacted_text(_decode_body(call.get("body")))}


def _redacted_url(url: Any) -> Any:
    """``url`` with the values of credential query parameters masked."""
    if not isinstance(url, str) or "?" not in url:
        return url
    import urllib.parse
    parts = urllib.parse.urlsplit(url)
    query = [(name, REDACTED if name.lower() in _SENSITIVE_QUERY else value)
             for name, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query, safe="<>")))


def _redacted_text(text: Optional[str]) -> Optional[str]:
    """A JSON body with credential members masked; anything else as it came."""
    if not text:
        return text
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return text
    return json.dumps(_redacted_json(data), sort_keys=True)


def _redacted_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: REDACTED if str(key).lower() in SENSITIVE_ARGUMENT_NAMES else _redacted_json(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted_json(item) for item in value]
    return value


def _headers_match(recorded: Mapping[str, Any], live: Mapping[str, Any]) -> bool:
    """Every recorded header is sent again with the same value (case-insensitive name).

    Redacted headers are not compared: their recorded value is gone.
    """
    sent = {str(name).lower(): value for name, value in live.items()}
    return all(value == REDACTED or sent.get(str(name).lower()) == value
               for name, value in dict(recorded or {}).items())


def _check_match_on(match_on: Sequence[str]) -> None:
    """Refuse a field that cannot be compared.

    An unknown field (``"methd"``) matched every request, and ``"headers"`` was
    recorded but never compared, so tenant B was served tenant A's response.
    """
    unknown = [field for field in match_on if field not in _MATCH_FIELDS]
    if unknown:
        raise ValueError(f"match_on fields must be among {_MATCH_FIELDS}, not {unknown}")


def _matches(recorded: Mapping[str, Any], call: Mapping[str, Any],
             match_on: Sequence[str]) -> bool:
    view = _request_view(call)
    for field in match_on:
        if field == "headers":
            if not _headers_match(recorded.get("headers", {}), dict(call.get("headers") or {})):
                return False
        elif recorded.get(field) != view[field]:
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
        """Append one request/response interaction, credentials redacted."""
        recorded_response = dict(response)
        if "headers" in recorded_response:
            recorded_response["headers"] = _redacted(recorded_response["headers"])
        # http_request also hands every Set-Cookie back in its own list.
        if isinstance(recorded_response.get("set_cookie"), list):
            recorded_response["set_cookie"] = [REDACTED] * len(recorded_response["set_cookie"])
        if "json" in recorded_response:
            recorded_response["json"] = _redacted_json(recorded_response["json"])
        if isinstance(recorded_response.get("text"), str):
            recorded_response["text"] = _redacted_text(recorded_response["text"])
        self._interactions.append({"request": _request_view(call),
                                   "response": recorded_response})

    def replay(self, call: Mapping[str, Any], *,
               match_on: Sequence[str] = ("method", "url")) -> Dict[str, Any]:
        """Return the recorded response for a matching ``call`` (no network)."""
        _check_match_on(match_on)
        for interaction in self._interactions:
            if _matches(interaction.get("request", {}), call, match_on):
                return dict(interaction["response"])
        raise CassetteMissError(
            f"no recorded interaction for {call.get('method')} {call.get('url')}")

    def replay_transport(self, *,
                         match_on: Sequence[str] = ("method", "url")) -> Transport:
        """Return a transport that replays from this cassette."""
        _check_match_on(match_on)
        return lambda call: self.replay(call, match_on=match_on)

    def recording_transport(self, inner: Transport) -> Transport:
        """Return a transport that records ``inner``'s live responses."""
        def transport(call: Mapping[str, Any]) -> Dict[str, Any]:
            response = inner(call)
            self.record(call, response)
            return response
        return transport
