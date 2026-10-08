"""Search index over the MCP tool registry: summaries first, one schema on request.

The registry holds several hundred tools and their descriptors run to a
couple of hundred kilobytes, which is what ``tools/list`` sends when a server
runs in its default, full mode. :class:`ToolIndex` is the other way to learn
what exists: a query returns a bounded number of :class:`ToolSummary` rows --
a name, one sentence, a category and the capability the tool needs -- and
:meth:`ToolIndex.get_schema` returns the full descriptor of one tool.

An index is an immutable snapshot of the tools it was built from. It never
reads the registry itself, so whoever builds it decides what is in it:
:class:`~je_auto_control.utils.mcp_server.disclosure.ToolDisclosure` builds
one per registry revision from the tools the current caller may call, which
is why a tool the caller's role or the server's read-only mode rules out
cannot be found here either.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.mcp_server._argument_policy import (
    PATH_FORMAT, PATH_OR_OTHER_FORMAT, VALUE_REF_FORMAT,
)
from je_auto_control.utils.mcp_server.tools._base import MCPTool, MCPToolDescriptor
from je_auto_control.utils.rbac.policy import capability_for_tool
from je_auto_control.utils.rbac.users import Capability

DEFAULT_SEARCH_LIMIT = 10
#: The most rows one search may return, whatever the caller asks for.
MAX_SEARCH_LIMIT = 50
MAX_QUERY_CHARS = 200
#: Longest summary sentence; a longer first sentence is cut at a word.
SUMMARY_CHARS = 160
#: Category of a tool a plugin registered, which no factory named.
PLUGIN_CATEGORY = "plugin"
UNCATEGORISED = "general"
_PLUGIN_PREFIX = "plugin_"

_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_PATH_FORMATS = frozenset({PATH_FORMAT, PATH_OR_OTHER_FORMAT, VALUE_REF_FORMAT})
_MAX_SCHEMA_DEPTH = 32

_EXACT_NAME, _NAME_WORD, _NAME_PART, _CATEGORY_WORD, _TEXT_WORD, _TEXT_PART = 100, 10, 6, 5, 2, 1


class ToolDiscoveryError(AutoControlException, ValueError):
    """A search or schema request the index cannot answer as asked."""


@dataclass(frozen=True)
class ToolSummary:
    """What a search says about one tool: enough to choose it, not to call it."""

    name: str
    summary: str
    category: str
    #: The :class:`~je_auto_control.utils.rbac.users.Capability` a call needs.
    capability: str
    read_only: bool
    #: Whether an argument names a file, which the server's path roots confine.
    takes_paths: bool

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON shape of one search row."""
        return {
            "name": self.name, "summary": self.summary, "category": self.category,
            "capability": self.capability, "read_only": self.read_only,
            "takes_paths": self.takes_paths,
        }


@dataclass(frozen=True)
class _Entry:
    """One indexed tool with the word sets a query is scored against."""

    tool: MCPTool
    summary: ToolSummary
    name: str
    name_words: FrozenSet[str]
    category_words: FrozenSet[str]
    text: str
    text_words: FrozenSet[str]


def category_of(tool: MCPTool) -> str:
    """The category ``tool`` is filed under in the index."""
    if tool.category:
        return tool.category
    return PLUGIN_CATEGORY if tool.name.startswith(_PLUGIN_PREFIX) else UNCATEGORISED


def summarise(description: str) -> str:
    """The first sentence of ``description``, cut to :data:`SUMMARY_CHARS`."""
    text = " ".join(description.split())
    sentence = _SENTENCE_END.split(text, maxsplit=1)[0]
    if len(sentence) <= SUMMARY_CHARS:
        return sentence
    return sentence[:SUMMARY_CHARS].rsplit(" ", 1)[0] + "..."


def _names_a_path(node: Any, depth: int = 0) -> bool:
    """Whether a schema node, or anything under it, is a path or value reference."""
    if depth > _MAX_SCHEMA_DEPTH:
        return False
    if isinstance(node, list):
        return any(_names_a_path(item, depth + 1) for item in node)
    if not isinstance(node, dict):
        return False
    if node.get("format") in _PATH_FORMATS:
        return True
    return any(_names_a_path(value, depth + 1) for value in node.values())


def _entry(tool: MCPTool) -> _Entry:
    category = category_of(tool)
    name = tool.name.lower()
    text = tool.description.lower()
    summary = ToolSummary(
        name=tool.name, summary=summarise(tool.description), category=category,
        capability=capability_for_tool(tool.name, tool.annotations.read_only),
        read_only=tool.annotations.read_only,
        takes_paths=_names_a_path(tool.input_schema),
    )
    return _Entry(
        tool=tool, summary=summary, name=name,
        name_words=frozenset(_WORD.findall(name)),
        category_words=frozenset(_WORD.findall(category.lower())),
        text=text, text_words=frozenset(_WORD.findall(text)),
    )


def _word_score(entry: _Entry, word: str) -> int:
    """How strongly one query word points at ``entry``; 0 when it does not."""
    if word in entry.name_words:
        return _NAME_WORD
    if word in entry.name:
        return _NAME_PART
    if word in entry.category_words:
        return _CATEGORY_WORD
    if word in entry.text_words:
        return _TEXT_WORD
    return _TEXT_PART if word in entry.text else 0


def _score(entry: _Entry, query: str, words: List[str]) -> int:
    score = sum(_word_score(entry, word) for word in words)
    return score + _EXACT_NAME if entry.name == query else score


def checked_limit(limit: Any) -> int:
    """``limit`` when it is an integer from 1 to :data:`MAX_SEARCH_LIMIT`, else an error."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ToolDiscoveryError(f"limit must be an integer, got {type(limit).__name__}")
    if not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ToolDiscoveryError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}, got {limit}")
    return limit


def _checked_query(query: Any) -> str:
    if not isinstance(query, str):
        raise ToolDiscoveryError(f"query must be a string, got {type(query).__name__}")
    if len(query) > MAX_QUERY_CHARS:
        raise ToolDiscoveryError(f"query is longer than {MAX_QUERY_CHARS} characters")
    return query.strip().lower()


class ToolIndex:
    """An immutable, searchable snapshot of a set of tools.

    ``version`` is whatever revision of the registry the tools were read at;
    two indexes with different versions may disagree, one index never changes.
    """

    def __init__(self, tools: Iterable[MCPTool], *, version: int = 0) -> None:
        self._entries: Tuple[_Entry, ...] = tuple(_entry(tool) for tool in tools)
        self._by_name: Dict[str, _Entry] = {entry.tool.name: entry for entry in self._entries}
        self._version = int(version)
        categories: Dict[str, int] = {}
        for entry in self._entries:
            categories[entry.summary.category] = categories.get(entry.summary.category, 0) + 1
        self._categories = categories

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    @property
    def version(self) -> int:
        """The registry revision this snapshot was taken at."""
        return self._version

    def categories(self) -> Dict[str, int]:
        """Every category in the index with the number of tools in it."""
        return dict(self._categories)

    def matches(self, query: str, *, category: Optional[str] = None,
                capability: Optional[str] = None) -> List[ToolSummary]:
        """Every tool matching ``query`` and the filters, best match first.

        An empty query matches everything the filters leave, in registry
        order. Raises :class:`ToolDiscoveryError` for a query that is not
        text or is too long, a category the index does not hold, or a
        capability that is not one of
        :class:`~je_auto_control.utils.rbac.users.Capability`.
        """
        text = _checked_query(query)
        candidates = self._filtered(category, capability)
        words = _WORD.findall(text)
        if not words:
            return [entry.summary for entry in candidates] if not text else []
        scored = [(_score(entry, text, words), position, entry)
                  for position, entry in enumerate(candidates)]
        ranked = sorted((item for item in scored if item[0] > 0),
                        key=lambda item: (-item[0], item[1]))
        return [entry.summary for _score_value, _position, entry in ranked]

    def search(self, query: str, *, limit: int = DEFAULT_SEARCH_LIMIT,
               category: Optional[str] = None,
               capability: Optional[str] = None) -> List[ToolSummary]:
        """The ``limit`` best matches for ``query``: summaries, never schemas.

        ``limit`` must be an integer from 1 to :data:`MAX_SEARCH_LIMIT`; the
        other arguments are checked as :meth:`matches` checks them.
        """
        bounded = checked_limit(limit)
        return self.matches(query, category=category, capability=capability)[:bounded]

    def get_schema(self, name: str) -> MCPToolDescriptor:
        """The full descriptor of the one tool called ``name``.

        Raises :class:`ToolDiscoveryError` when the index has no such tool,
        which is also the answer for one the caller may not use.
        """
        return self.tool(name).descriptor()

    def tool(self, name: str) -> MCPTool:
        """The indexed tool called ``name``; :class:`ToolDiscoveryError` if absent."""
        entry = self._by_name.get(name) if isinstance(name, str) else None
        if entry is None:
            raise ToolDiscoveryError(f"no tool named {name!r} is available to this caller")
        return entry.tool

    def _filtered(self, category: Optional[str],
                  capability: Optional[str]) -> List[_Entry]:
        if category is not None and category not in self._categories:
            raise ToolDiscoveryError(
                f"unknown category {category!r}; known: {sorted(self._categories)}")
        if capability is not None and capability not in Capability.all():
            raise ToolDiscoveryError(
                f"unknown capability {capability!r}; known: {Capability.all()}")
        return [entry for entry in self._entries
                if (category is None or entry.summary.category == category)
                and (capability is None or entry.summary.capability == capability)]


__all__ = [
    "DEFAULT_SEARCH_LIMIT", "MAX_QUERY_CHARS", "MAX_SEARCH_LIMIT", "PLUGIN_CATEGORY",
    "ToolDiscoveryError", "ToolIndex", "ToolSummary", "category_of", "checked_limit",
    "summarise",
]
