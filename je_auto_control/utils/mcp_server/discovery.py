"""Bounded, authority-filtered tool summaries and detached schemas from one registry snapshot."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import TYPE_CHECKING, Any, Iterable, Literal, TypedDict

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.authorization import current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import capability_for_tool
from je_auto_control.utils.mcp_server.tools._base import MCPTool

if TYPE_CHECKING:
    import threading

ToolCategory = Literal["agents", "browser", "desktop", "files", "data", "system", "extension", "other"]


class ToolDiscoveryError(AutoControlException, ValueError):
    """Discovery inputs are invalid or a tool is unavailable to this caller."""


class ToolSummary(TypedDict):
    """Small discovery result; schema is returned only by explicit single-tool lookup."""

    name: str
    description: str
    category: ToolCategory
    capability: str
    read_only: bool


def _query(query: str, limit: int) -> str:
    if not isinstance(query, str) or len(query) > 256:
        raise ToolDiscoveryError("query must be text of at most 256 characters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ToolDiscoveryError("limit must be an integer from 1 to 50")
    return " ".join(query.casefold().split())


def _matches(item: ToolSummary, tokens: list[str]) -> bool:
    text = (item["name"] + " " + item["description"]).casefold()
    return all(token in text for token in tokens)


def _category(tool: MCPTool) -> ToolCategory:
    module = getattr(tool.handler, "__module__", "")
    groups: tuple[tuple[ToolCategory, tuple[str, ...]], ...] = (
        ("agents", ("agent", "skill")), ("browser", ("web",)),
        ("desktop", ("mouse", "keyboard", "window", "screen", "a11y", "ocr", "image")),
        ("files", ("file", "pdf", "office")), ("data", ("data", "json", "csv", "sql", "text")),
        ("system", ("system", "host", "process", "diagnos", "capabil", "mcp")),
    )
    for category, words in groups:
        if any(word in tool.name.removeprefix("ac_") for word in words):
            return category
    return "extension" if "plugin" in module else "other"


class ToolIndex:
    """Keep detached registry metadata; refresh the caller's role on every query."""

    def __init__(self, tools: Iterable[MCPTool]) -> None:
        self._entries: dict[str, tuple[ToolSummary, dict[str, Any]]] = {}
        for tool in tools:
            summary = ToolSummary(name=tool.name, description=tool.description[:240], category=_category(tool),
                                  capability=capability_for_tool(tool.name, tool.annotations.read_only),
                                  read_only=tool.annotations.read_only)
            self._entries[tool.name] = (summary, deepcopy(tool.to_descriptor()))
        serialized = json.dumps([self._entries[name] for name in sorted(self._entries)],
                                sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self._snapshot_id = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def snapshot_id(self) -> str:
        """Identify the full metadata snapshot, independent of later registry edits."""
        return self._snapshot_id

    def search(self, query: str, *, limit: int = 10) -> list[ToolSummary]:
        """Rank a bounded plain-text query without returning full schemas or invoking tools."""
        query = _query(query, limit)
        with DeferredAuthorization.capture().context_scope() as caller:
            candidates = [summary for summary, _ in self._entries.values()
                          if caller is None or caller.allows(summary["capability"])]
        tokens = query.split()
        matches = [item for item in candidates if _matches(item, tokens)]
        matches.sort(key=lambda item: (item["name"].casefold() != query,
                                      not item["name"].casefold().startswith(query), item["name"]))
        return deepcopy(matches[:limit])

    def get_schema(self, name: str) -> dict[str, Any]:
        """Return one detached descriptor only if the current caller may invoke the tool."""
        if not isinstance(name, str) or not 1 <= len(name) <= 256:
            raise ToolDiscoveryError("tool name must be bounded nonempty text")
        entry = self._entries.get(name)
        with DeferredAuthorization(current_authorization()).context_scope() as caller:
            if entry is None or (caller is not None and not caller.allows(entry[0]["capability"])):
                raise ToolDiscoveryError("tool is not available")
        return deepcopy(entry[1])


def search_mcp_tools(query: str, *, limit: int = 10, read_only: bool | None = None) -> list[ToolSummary]:
    """Search the current default registry without starting a transport or loading native backends."""
    # pylint: disable-next=import-outside-toplevel  # reason: the factories depend on this module's types
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return ToolIndex(build_default_tool_registry(read_only=read_only)).search(query, limit=limit)


def get_mcp_tool_schema(name: str, *, read_only: bool | None = None) -> dict[str, Any]:
    """Inspect a single current default-registry schema under the caller's role and read-only filter."""
    # pylint: disable-next=import-outside-toplevel  # reason: the factories depend on this module's types
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return ToolIndex(build_default_tool_registry(read_only=read_only)).get_schema(name)


# pylint: disable-next=too-few-public-methods  # reason: a single host registry seam, not a standalone service
class ToolCatalogMixin:
    """Snapshot the host's actual registry, including read-only filters and plugin changes."""

    if TYPE_CHECKING:
        _tools_lock: threading.Lock
        _tools: dict[str, MCPTool]

    def tool_index(self) -> ToolIndex:
        """Copy metadata under the registry lock; queries never invoke plugin handlers."""
        with self._tools_lock:
            return ToolIndex(self._tools.values())
