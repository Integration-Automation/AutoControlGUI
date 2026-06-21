"""Parse RFC 9457 ``application/problem+json`` error responses.

``http_request`` returns a non-2xx body unparsed, so a flow (or ``assert_http``)
had no structured way to read a standardised API error. This reads the RFC 9457
problem document — the registered ``type`` / ``title`` / ``status`` / ``detail``
/ ``instance`` members plus any vendor extensions.

Pure standard library (``json``); imports no ``PySide6``. Every function is pure
(response dict in, dataclass out) so it is fully deterministic in CI.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException

_PROBLEM_MEDIA_TYPE = "application/problem+json"
_REGISTERED = ("type", "title", "status", "detail", "instance")


class HttpProblemError(AutoControlException):
    """Raised by :func:`raise_for_problem` when a response is a problem."""

    def __init__(self, problem: "ProblemDetails") -> None:
        super().__init__(problem.summary())
        self.problem = problem


@dataclass(frozen=True)
class ProblemDetails:
    """An RFC 9457 problem document."""

    type: str = "about:blank"
    title: Optional[str] = None
    status: Optional[int] = None
    detail: Optional[str] = None
    instance: Optional[str] = None
    extensions: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """A short ``status title — detail`` description."""
        head = " ".join(str(part) for part in (self.status, self.title) if part)
        return f"{head} — {self.detail}" if self.detail else (head or self.type)

    def to_dict(self) -> Dict[str, Any]:
        """Return the document as a flat dict (extensions merged in)."""
        out: Dict[str, Any] = {"type": self.type}
        for name in ("title", "status", "detail", "instance"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        out.update(self.extensions)
        return out


def is_problem(headers: Optional[Mapping[str, Any]]) -> bool:
    """Whether ``headers`` advertise an ``application/problem+json`` body."""
    for key, value in (headers or {}).items():
        if str(key).lower() == "content-type":
            return _PROBLEM_MEDIA_TYPE in str(value).lower()
    return False


def _coerce_status(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _from_document(document: Mapping[str, Any]) -> ProblemDetails:
    extensions = {key: value for key, value in document.items()
                  if key not in _REGISTERED}
    return ProblemDetails(
        type=str(document.get("type", "about:blank")),
        title=document.get("title"),
        status=_coerce_status(document.get("status")),
        detail=document.get("detail"),
        instance=document.get("instance"),
        extensions=extensions)


def parse_problem(response: Mapping[str, Any]) -> Optional[ProblemDetails]:
    """Parse a problem document from an ``http_request`` response, or ``None``.

    Returns ``None`` unless the response advertises ``application/problem+json``
    and carries a JSON object body.
    """
    if not is_problem(response.get("headers")):
        return None
    document = response.get("json")
    if document is None and response.get("text"):
        try:
            document = json.loads(response["text"])
        except (ValueError, TypeError):
            return None
    if not isinstance(document, dict):
        return None
    return _from_document(document)


def raise_for_problem(response: Mapping[str, Any]) -> None:
    """Raise :class:`HttpProblemError` when ``response`` is a problem document."""
    problem = parse_problem(response)
    if problem is not None:
        raise HttpProblemError(problem)
