"""Parse RFC 8288 ``Link`` headers and follow ``rel="next"`` pagination.

Paginated REST APIs return ``Link: <...>; rel="next"`` headers, but nothing
parsed them, so multi-page fetches needed manual glue. This parses the header
(handling quoted parameter values and multiple links), indexes links by their
relation, and walks ``rel="next"`` over an injected transport.

Pure standard library (``re``); imports no ``PySide6``. The parser is pure and
``paginate`` takes an injected ``fetch`` callable, so pagination is CI-testable
without a live server.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

_LINK_RE = re.compile(r"<([^>]*)>\s*(;[^<]*)?")

Links = Union[str, List["Link"]]
Fetch = Callable[[str], Mapping[str, Any]]


@dataclass(frozen=True)
class Link:
    """One RFC 8288 web link."""

    uri: str
    rel: Optional[str] = None
    params: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly view of the link."""
        return {"uri": self.uri, "rel": self.rel, "params": dict(self.params)}


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_params(chunk: Optional[str]) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for part in (chunk or "").split(";"):
        cleaned = part.strip().rstrip(",").strip()
        if not cleaned:
            continue
        key, sep, value = cleaned.partition("=")
        key = key.strip().lower()
        if key and sep:
            params[key] = _strip_quotes(value.strip().rstrip(",").strip())
    return params


def parse_link_header(value: Optional[str]) -> List[Link]:
    """Parse a ``Link`` header value into a list of :class:`Link`."""
    links: List[Link] = []
    for match in _LINK_RE.finditer(value or ""):
        params = _parse_params(match.group(2))
        links.append(Link(uri=match.group(1).strip(),
                          rel=params.get("rel"), params=params))
    return links


def _as_links(links: Links) -> List[Link]:
    return parse_link_header(links) if isinstance(links, str) else list(links)


def links_by_rel(links: Links) -> Dict[str, Link]:
    """Index links by each (possibly space-separated) relation; last wins."""
    indexed: Dict[str, Link] = {}
    for link in _as_links(links):
        for token in (link.rel or "").split():
            indexed[token] = link
    return indexed


def next_url(links: Links) -> Optional[str]:
    """Return the ``rel="next"`` URI, if any."""
    link = links_by_rel(links).get("next")
    return link.uri if link is not None else None


def _link_header_of(headers: Optional[Mapping[str, Any]]) -> Optional[str]:
    for key, value in (headers or {}).items():
        if str(key).lower() == "link":
            return str(value)
    return None


def paginate(url: str, fetch: Fetch, *,
             max_pages: int = 100) -> List[Mapping[str, Any]]:
    """Fetch ``url`` then follow ``rel="next"`` Link headers via ``fetch``.

    ``fetch`` maps a URL to a response mapping with a ``headers`` dict. Stops at
    ``max_pages`` or when no ``next`` link is present. Returns each response.
    """
    responses: List[Mapping[str, Any]] = []
    current: Optional[str] = url
    while current and len(responses) < max_pages:
        response = fetch(current)
        responses.append(response)
        header = _link_header_of(response.get("headers"))
        current = next_url(header) if header else None
    return responses
