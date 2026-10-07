"""Owned session tool availability with coherent bounded snapshot pagination."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import secrets
import threading
import time
from typing import Callable, Literal, Sequence

from je_auto_control.utils.mcp_server._disclosure_cursor import CursorSigner
from je_auto_control.utils.mcp_server.discovery import (
    MCPToolDescriptor, ToolDiscoveryError, ToolIndex, default_tool_index,
)

DisclosureMode = Literal['full', 'progressive', 'static']
CORE_TOOLS = frozenset(('ac_probe_capabilities', 'ac_discover_tools', 'ac_get_tool_schema',
                        'ac_enable_tools', 'ac_disable_tools', 'ac_tool_state'))
SNAPSHOT_TTL_S = 120.0
MAX_SNAPSHOTS = 8
MAX_SELECTED_TOOLS = 1000


class ToolDisclosureError(ToolDiscoveryError):
    """Invalid disclosure settings, closed view or stale/foreign cursor."""


@dataclass(frozen=True)
class DisclosureResult:
    """One idempotent availability change, not an execution authorization."""
    changed: bool
    names: tuple[str, ...]
    version: int

    def to_dict(self) -> dict[str, object]:
        """Serialize a session-local change result."""
        return {'changed': self.changed, 'names': list(self.names), 'version': self.version}


@dataclass(frozen=True)
class ToolPage:
    """A page of copied descriptors from one stable snapshot/version."""
    tools: tuple[MCPToolDescriptor, ...]
    next_cursor: str | None
    snapshot_id: str
    version: int

    def to_dict(self) -> dict[str, object]:
        """Use MCP nextCursor spelling; absence preserves the unpaged full result."""
        result: dict[str, object] = {'tools': [tool.to_dict() for tool in self.tools],
                                    'snapshotId': self.snapshot_id, 'registryVersion': self.version}
        if self.next_cursor is not None:
            result['nextCursor'] = self.next_cursor
        return result


@dataclass(frozen=True)
class _Snapshot:
    identifier: str
    index: ToolIndex
    names: tuple[str, ...]
    expires_at: float


def _names(names: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(names, Sequence) or isinstance(names, (str, bytes)) or len(names) > 100:
        raise ToolDisclosureError('names must be a sequence of at most 100 tool names')
    if any(not isinstance(name, str) or not name or len(name) > 256 for name in names):
        raise ToolDisclosureError('names must contain nonempty strings up to 256 characters')
    return tuple(dict.fromkeys(names))


class ToolView:  # pylint: disable=too-many-instance-attributes  # reason: separate policy, owner state and cursor cache
    """One owner/session's view; a fresh supplier provides the live registry and current policy."""

    def __init__(self, index: Callable[[], ToolIndex], *, mode: DisclosureMode = 'progressive',
                 profile: Sequence[str] = (), page_size: int | None = None,
                 notify: Callable[[], None] | None = None) -> None:
        if mode not in ('full', 'progressive', 'static'):
            raise ToolDisclosureError('mode must be full, progressive or static')
        if page_size is not None and (isinstance(page_size, bool) or not isinstance(page_size, int)
                                      or not 1 <= page_size <= 100):
            raise ToolDisclosureError('page_size must be an integer from 1 to 100')
        selected = _names(profile)
        if selected and mode != 'static':
            raise ToolDisclosureError('profile requires static mode')
        self.mode = mode
        self._index = index
        self._selected = set(selected)
        self._page_size = page_size if page_size is not None else (None if mode == 'full' else 50)
        self._notify = notify
        self._lock = threading.Lock()
        self._closed = False
        self._snapshots: OrderedDict[str, _Snapshot] = OrderedDict()
        self._signer = CursorSigner(secrets.token_bytes(32))

    def _require_open(self) -> None:
        if self._closed:
            raise ToolDisclosureError('tool view closed')

    def _current_index(self) -> ToolIndex:
        with self._lock:
            self._require_open()
        return self._index()

    def _visible(self, index: ToolIndex) -> tuple[str, ...]:
        with self._lock:
            self._require_open()
            selected = set(self._selected) | CORE_TOOLS
        return tuple(name for name in index.authorized_names() if self.mode == 'full' or name in selected)

    @property
    def visible_names(self) -> tuple[str, ...]:
        """Live authorized visible names; removed tools disappear immediately."""
        return self._visible(self._current_index())

    @property
    def snapshot_count(self) -> int:
        """Number of retained cursored snapshots; single-page replies retain none."""
        with self._lock:
            self._expire()
            return len(self._snapshots)

    def _expire(self) -> None:
        expired = [key for key, value in self._snapshots.items() if value.expires_at <= time.monotonic()]
        for key in expired:
            del self._snapshots[key]

    def enable(self, names: Sequence[str]) -> DisclosureResult:
        """Atomically enable valid authorized names in this progressive view only."""
        return self._change(names, enable=True)

    def disable(self, names: Sequence[str]) -> DisclosureResult:
        """Disable selected tools; core discovery tools remain available."""
        return self._change(names, enable=False)

    def _change(self, names: Sequence[str], *, enable: bool) -> DisclosureResult:
        selected = _names(names)
        index = self._current_index()
        if enable:
            for name in selected:
                index.get_schema(name)
        with self._lock:
            self._require_open()
            if self.mode != 'progressive':
                raise ToolDisclosureError(f'{self.mode} view does not allow availability changes')
            previous = set(self._selected)
            if enable:
                updated = self._selected | (set(selected) - CORE_TOOLS)
                if len(updated) > MAX_SELECTED_TOOLS:
                    raise ToolDisclosureError("selection exceeds 1000 tools; disable unused names first")
                self._selected = updated
            else:
                self._selected.difference_update(set(selected) - CORE_TOOLS)
            changed = previous != self._selected
        if changed and self._notify is not None:
            self._notify()
        return DisclosureResult(changed, self._visible(index), index.version)

    def list_page(self, cursor: str | None = None) -> ToolPage:
        """List one stable snapshot; foreign, expired or revoked-permission cursors fail explicitly."""
        if cursor is None:
            index = self._current_index()
            snapshot = _Snapshot(secrets.token_urlsafe(16), index, self._visible(index),
                                 time.monotonic() + SNAPSHOT_TTL_S)
            offset = 0
        else:
            snapshot, offset = self._resolve_cursor(cursor)
        end = min(len(snapshot.names), offset + (self._page_size or len(snapshot.names)))
        # Schema lookup on the original snapshot still rechecks current authorization.
        try:
            tools = tuple(snapshot.index.get_schema(name) for name in snapshot.names[offset:end])
        except ToolDiscoveryError as error:
            raise ToolDisclosureError('cursor permissions changed; restart listing') from error
        next_cursor = self._retain(snapshot, end) if end < len(snapshot.names) else None
        with self._lock:
            self._require_open()
        return ToolPage(tools, next_cursor, snapshot.identifier, snapshot.index.version)

    def _resolve_cursor(self, cursor: str) -> tuple[_Snapshot, int]:
        try:
            identifier, offset = self._signer.decode(cursor)
        except ValueError as error:
            raise ToolDisclosureError('invalid cursor') from error
        with self._lock:
            self._require_open()
            self._expire()
            snapshot = self._snapshots.get(identifier)
        if snapshot is None or offset >= len(snapshot.names):
            raise ToolDisclosureError('stale cursor; restart listing')
        return snapshot, offset

    def _retain(self, snapshot: _Snapshot, offset: int) -> str:
        with self._lock:
            self._require_open()
            self._expire()
            self._snapshots[snapshot.identifier] = snapshot
            while len(self._snapshots) > MAX_SNAPSHOTS:
                self._snapshots.popitem(last=False)
        return self._signer.encode(snapshot.identifier, offset)

    def state(self) -> dict[str, object]:
        """Read current mode and live authorized names without changing availability."""
        index = self._current_index()
        return {'mode': self.mode, 'names': list(self._visible(index)), 'version': index.version}

    def close(self) -> None:
        """Revoke this owner immediately and reclaim all selections and cursors."""
        with self._lock:
            self._closed = True
            self._selected.clear()
            self._snapshots.clear()


def preview_tool_disclosure(mode: DisclosureMode = 'progressive', names: Sequence[str] = (),
                            profile: Sequence[str] = (), *, index: ToolIndex | None = None) -> dict[str, object]:
    """Inspect an isolated availability view; never alter a serving session or invoke tools."""
    selected = _names(names)
    chosen = index if index is not None else default_tool_index()
    view = ToolView(lambda: chosen, mode=mode, profile=profile)
    try:
        if selected:
            view.enable(selected)
        visible = view.visible_names
        return {'mode': view.mode, 'names': list(visible), 'version': chosen.version,
                'tools': [chosen.get_schema(name).to_dict() for name in visible]}
    finally:
        view.close()
