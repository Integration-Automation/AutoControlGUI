"""Registry-only typed MCP search snapshots with bounded replies and current authorization."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence, cast

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.mcp_server.tools._base import MCPTool, ToolCategory, read_only_env_flag
from je_auto_control.utils.rbac.authorization import permitted, required_capability
from je_auto_control.utils.rbac.users import Capability

ToolCapability = Literal['read_screen', 'drive_input', 'manage_hosts', 'manage_users', 'read_audit']


class ToolDiscoveryError(AutoControlException, ValueError):
    """Invalid discovery request or an unavailable/unauthorized tool."""


@dataclass(frozen=True)
class ToolSummary:
    """Compact non-schema metadata; requirements come from the reviewed RBAC catalog."""
    name: str
    description: str
    category: ToolCategory
    required_capability: ToolCapability
    read_only: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize a bounded summary without input/output schemas."""
        return {'name': self.name, 'description': self.description, 'category': self.category,
                'required_capability': self.required_capability, 'read_only': self.read_only}


@dataclass(frozen=True)
class MCPToolDescriptor:
    """Single-tool descriptor with copy-on-export schema ownership."""
    name: str
    _descriptor: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return an independent full descriptor of this tool only."""
        return deepcopy(self._descriptor)


@dataclass(frozen=True)
class _Entry:
    tool: MCPTool
    summary: ToolSummary
    descriptor: MCPToolDescriptor


class ToolIndex:
    """Stable registry snapshot; authorization is checked again on every query."""

    def __init__(self, tools: Sequence[MCPTool], *, version: int = 0,
                 authorize: Callable[[MCPTool], bool] | None = None, read_only: bool | None = None) -> None:
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ToolDiscoveryError('version must be a nonnegative integer')
        self._version = version
        self._authorize = authorize
        if read_only is not None and not isinstance(read_only, bool):
            raise ToolDiscoveryError('read_only must be boolean')
        self._read_only = read_only_env_flag() if read_only is None else read_only
        entries = []
        names: set[str] = set()
        for tool in tools:
            if tool.name in names:
                raise ToolDiscoveryError(f'duplicate registry name: {tool.name}')
            names.add(tool.name)
            capability = required_capability(tool.name)
            if capability not in Capability.all():
                raise ToolDiscoveryError('unknown reviewed capability')
            summary = ToolSummary(tool.name, tool.description[:240], tool.category,
                                  cast(ToolCapability, capability), tool.annotations.read_only)
            descriptor = MCPToolDescriptor(tool.name, deepcopy(tool.to_descriptor()))
            entries.append(_Entry(tool, summary, descriptor))
        self._entries = tuple(entries)

    @property
    def version(self) -> int:
        """Registry mutation version belonging to this immutable entry snapshot."""
        return self._version

    def _allowed(self, entry: _Entry) -> bool:
        if self._read_only and not entry.summary.read_only:
            return False
        if not permitted(entry.tool.name, read_only=entry.summary.read_only):
            return False
        return self._authorize is None or self._authorize(entry.tool)

    def search(self, query: str, *, limit: int = 10) -> list[ToolSummary]:
        """Return deterministic ranked summaries, at most 100, from this authorized snapshot."""
        terms = _search_terms(query, limit)
        matches = []
        for entry in self._entries:
            text = f'{entry.summary.name} {entry.tool.description} {entry.summary.category}'.casefold()
            if self._allowed(entry) and all(term in text for term in terms):
                score = sum(term in entry.summary.name.casefold() for term in terms)
                matches.append((score, entry.summary))
        matches.sort(key=lambda row: (-row[0], row[1].name))
        return [summary for _, summary in matches[:limit]]

    def get_schema(self, name: str) -> MCPToolDescriptor:
        """Return one copied descriptor; denied and absent names share an unavailable error."""
        if not isinstance(name, str) or not name or len(name) > 256:
            raise ToolDiscoveryError('name must be a nonempty string up to 256 characters')
        for entry in self._entries:
            if entry.summary.name == name and self._allowed(entry):
                return MCPToolDescriptor(name, entry.descriptor.to_dict())
        raise ToolDiscoveryError('tool unavailable')


def _search_terms(query: str, limit: int) -> list[str]:
    """Bound query text and requested reply size before scanning the registry."""
    if not isinstance(query, str) or len(query) > 512:
        raise ToolDiscoveryError('query must be a string up to 512 characters')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ToolDiscoveryError('limit must be an integer from 1 to 100')
    return query.casefold().split()


def default_tool_index() -> ToolIndex:
    """Build the local default registry snapshot without Qt, native probes or calls."""
    # pylint: disable-next=import-outside-toplevel  # reason: registry factories refer back to these handlers
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    return ToolIndex(build_default_tool_registry())


def discover_tools(query: str = '', *, limit: int = 10) -> dict[str, object]:
    """Search the authorized local registry; remote handlers use their actual server snapshot."""
    index = default_tool_index()
    return {'version': index.version, 'tools': [row.to_dict() for row in index.search(query, limit=limit)]}


def get_tool_schema(name: str) -> dict[str, Any]:
    """Get one authorized local-registry schema without executing its handler."""
    return default_tool_index().get_schema(name).to_dict()


__all__ = ['MCPToolDescriptor', 'ToolCapability', 'ToolDiscoveryError', 'ToolIndex', 'ToolSummary',
           'default_tool_index', 'discover_tools', 'get_tool_schema']
