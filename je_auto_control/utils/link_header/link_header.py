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
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union
from urllib.parse import urljoin

_OWS = " \t"
_RWS = re.compile(r"[ \t]+")
_NAME_END = frozenset(" \t=;,")

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


def _skip_ows(text: str, index: int) -> int:
    while index < len(text) and text[index] in _OWS:
        index += 1
    return index


def _quoted_string(text: str, index: int) -> Tuple[str, int]:
    """RFC 8288 B.4 from the ``"`` at ``index``: the unquoted value and the index after it."""
    out: List[str] = []
    index += 1
    while index < len(text):
        char = text[index]
        if char == '"':
            return "".join(out), index + 1
        if char == "\\":
            index += 1
            if index >= len(text):
                break
            char = text[index]
        out.append(char)
        index += 1
    return "".join(out), index


def _parameter_value(text: str, index: int) -> Tuple[str, int]:
    """B.3 step 7: a quoted string, or everything up to the next ``;`` or ``,``."""
    if text.startswith('"', index):
        return _quoted_string(text, index)
    end = index
    while end < len(text) and text[end] not in ";,":
        end += 1
    return text[index:end].rstrip(_OWS), end


def _parse_parameters(text: str, index: int) -> Tuple[List[Tuple[str, str]], int]:
    """RFC 8288 B.3: the ``(name, value)`` pairs after a ``<target>``; a valueless one is ``""``."""
    params: List[Tuple[str, str]] = []
    while True:
        index = _skip_ows(text, index)
        if not text.startswith(";", index):
            return params, index
        start = end = _skip_ows(text, index + 1)
        while end < len(text) and text[end] not in _NAME_END:
            end += 1
        index = _skip_ows(text, end)
        value = ""
        if text.startswith("=", index):
            value, index = _parameter_value(text, _skip_ows(text, index + 1))
        params.append((text[start:end].lower(), value))


def _first_of_each(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """RFC 8288 3.3: occurrences of a parameter after the first are ignored."""
    params: Dict[str, str] = {}
    for name, value in pairs:
        if name and name not in params:
            params[name] = value
    return params


def parse_link_header(value: Optional[str]) -> List[Link]:
    """Parse a ``Link`` header value into a list of :class:`Link` (RFC 8288 Appendix B.2).

    The value is read left to right: a ``<`` inside an unquoted parameter
    (``title=x<y``) or a comma inside a quoted one belongs to that parameter.
    The splitting regex used before took ``<y, <b>`` for a target, so the link
    after it vanished and ``next_url`` answered with the wrong page.
    Parsing stops at the first link that does not start with ``<``.
    """
    text, links, index = value or "", [], 0
    while index < len(text):
        index = _skip_ows(text, index)
        if text.startswith(",", index):          # an empty list element
            index += 1
            continue
        start = index + 1
        end = text.find(">", start) if text.startswith("<", index) else -1
        if end < 0:
            break
        pairs, index = _parse_parameters(text, end + 1)
        params = _first_of_each(pairs)
        links.append(Link(uri=text[start:end].strip(), rel=params.get("rel"), params=params))
        index = _skip_ows(text, index)
        if text.startswith(",", index):
            index += 1
    return links


def _as_links(links: Links) -> List[Link]:
    return parse_link_header(links) if isinstance(links, str) else list(links)


def links_by_rel(links: Links) -> Dict[str, Link]:
    """Index links by each (possibly space-separated) relation; last wins."""
    indexed: Dict[str, Link] = {}
    for link in _as_links(links):
        for token in filter(None, _RWS.split(link.rel or "")):
            indexed[token.lower()] = link   # relation types are case-insensitive
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
    A relative ``next`` link is resolved against the page it came from.
    """
    responses: List[Mapping[str, Any]] = []
    current: Optional[str] = url
    while current and len(responses) < max_pages:
        response = fetch(current)
        responses.append(response)
        header = _link_header_of(response.get("headers"))
        following = next_url(header) if header else None
        current = urljoin(current, following) if following else None
    return responses
