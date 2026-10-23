"""Session-local availability and bounded opaque cursors; disclosure never grants execution authority."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import secrets
import threading
import time
from typing import Any, Callable, Iterable, TypedDict

from je_auto_control.utils.mcp_server.discovery import ToolDiscoveryError, ToolIndex, ToolSummary
from je_auto_control.utils.mcp_server.tools._base import read_only_env_flag
from je_auto_control.utils.rbac.deferred import DeferredAuthorization

CORE_TOOLS = frozenset({"ac_mcp_tool_search", "ac_mcp_tool_schema", "ac_mcp_tools_state",
                        "ac_mcp_tools_enable", "ac_mcp_tools_disable"})
MODES = frozenset({"full", "progressive", "static"})


class ToolPage(TypedDict, total=False):
    """One snapshot page with a single-use opaque continuation when more names remain."""

    tools: list[dict[str, Any]]
    snapshot_id: str
    nextCursor: str


@dataclass(frozen=True)
class _Cursor:
    registry: str
    snapshot: str
    scope: tuple[str, str, str] | None
    names: tuple[str, ...]
    offset: int
    created: float


def _names(value: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or len(value) > 100:
        raise ToolDiscoveryError("names must be a list of at most 100 tool names")
    if not all(isinstance(name, str) and 1 <= len(name) <= 256 for name in value):
        raise ToolDiscoveryError("names must contain bounded nonempty tool names")
    return tuple(dict.fromkeys(value))


def _scope_key() -> tuple[str, str, str] | None:
    with DeferredAuthorization.capture().context_scope() as caller:
        return None if caller is None else (caller.user_id, caller.role, str(caller.store_path or ""))


class ToolView:
    """An owned availability view; live indexes recheck role grants and plugin membership."""

    def __init__(self, provider: Callable[[], ToolIndex], *, mode: str = "progressive",
                 initial: Iterable[str] = (), page_size: int = 50,
                 changed: Callable[[], None] | None = None) -> None:
        if not isinstance(mode, str) or mode not in MODES:
            raise ToolDiscoveryError("disclosure mode must be full, progressive or static")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ToolDiscoveryError("page_size must be an integer from 1 to 100")
        self._provider: Callable[[], ToolIndex] | None = provider
        self._mode, self._page_size = mode, page_size
        self._enabled = set(_names(initial))
        self._changed = changed
        self._lock = threading.RLock()
        self._cursors: dict[str, _Cursor] = {}

    def _index(self) -> ToolIndex:
        if self._provider is None:
            raise ToolDiscoveryError("tool view is closed")
        return self._provider()

    def _visible(self, index: ToolIndex) -> tuple[str, ...]:
        names = index.names()
        return names if self._mode == "full" else tuple(name for name in names if name in self._enabled | CORE_TOOLS)

    def search(self, query: str, *, limit: int = 10) -> list[ToolSummary]:
        """Search current authorized metadata even before enabling a tool."""
        with self._lock:
            return self._index().search(query, limit=limit)

    def get_schema(self, name: str) -> dict[str, Any]:
        """Inspect one authorized tool before deciding whether to disclose it."""
        with self._lock:
            return self._index().get_schema(name)

    def state(self) -> dict[str, Any]:
        """Describe current availability without full schemas or arguments."""
        with self._lock:
            index = self._index()
            position = self._position(index, None)
            return {"mode": self._mode, "enabled": list(position.names), "snapshot_id": position.snapshot}

    def enable(self, names: Iterable[str]) -> dict[str, Any]:
        """Atomically add authorized live names to this view, notifying only on change."""
        requested = _names(names)
        with self._lock:
            self._mutable()
            index = self._index()
            for name in requested:
                index.get_schema(name)
            changed = not set(requested) <= self._enabled | CORE_TOOLS
            self._enabled.update(requested)
            if changed:
                self._cursors.clear()
        self._notify(changed)
        return self.state()

    def disable(self, names: Iterable[str]) -> dict[str, Any]:
        """Remove names from this session; discovery controls themselves stay available."""
        requested = set(_names(names))
        if requested & CORE_TOOLS:
            raise ToolDiscoveryError("core discovery controls cannot be disabled")
        with self._lock:
            self._mutable()
            self._index()
            changed = bool(requested & self._enabled)
            self._enabled.difference_update(requested)
            if changed:
                self._cursors.clear()
        self._notify(changed)
        return self.state()

    def _mutable(self) -> None:
        if self._provider is None:
            raise ToolDiscoveryError("tool view is closed")
        if self._mode != "progressive":
            raise ToolDiscoveryError("this disclosure profile is fixed")

    def _notify(self, changed: bool) -> None:
        if changed and self._changed is not None:
            self._changed()

    def require_available(self, name: str) -> None:
        """Reject direct invocation of unavailable tools; the dispatcher still enforces arguments and authority."""
        with self._lock:
            if name not in self._visible(self._index()):
                raise ToolDiscoveryError("tool is not available in this session")

    def list_page(self, cursor: str | None = None) -> ToolPage:
        """Return a stable page or reject stale/foreign/expired cursors without mixing versions."""
        with self._lock:
            index = self._index()
            position = self._position(index, cursor)
            size = len(position.names) if self._mode == "full" else self._page_size
            end = position.offset + size
            result = ToolPage(tools=[index.get_schema(name) for name in position.names[position.offset:end]],
                              snapshot_id=position.snapshot)
            if end < len(position.names):
                token = secrets.token_urlsafe(24)
                self._cursors[token] = _Cursor(position.registry, position.snapshot, position.scope,
                                               position.names, end, time.monotonic())
                while len(self._cursors) > 8:
                    self._cursors.pop(next(iter(self._cursors)))
                result["nextCursor"] = token
            return result

    def _position(self, index: ToolIndex, cursor: str | None) -> _Cursor:
        scope = _scope_key()
        if cursor is None:
            names = self._visible(index)
            payload = json.dumps((index.snapshot_id, scope, names), separators=(",", ":")).encode("utf-8")
            return _Cursor(index.snapshot_id, hashlib.sha256(payload).hexdigest(), scope, names, 0, time.monotonic())
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 96:
            raise ToolDiscoveryError("invalid tool cursor")
        previous = self._cursors.pop(cursor, None)
        if previous is None or previous.registry != index.snapshot_id or previous.scope != scope:
            raise ToolDiscoveryError("stale or foreign tool cursor; restart tools/list")
        if time.monotonic() - previous.created > 300:
            raise ToolDiscoveryError("expired tool cursor; restart tools/list")
        return previous

    def close(self) -> None:
        """Retire this view and its cursors so outstanding callbacks cannot recreate it."""
        with self._lock:
            self._provider = None
            self._enabled.clear()
            self._cursors.clear()


def validate_tool_profile(index: ToolIndex, mode: str, names: Iterable[str], page_size: int) -> None:
    """Validate inert host settings against one effective registry snapshot without granting access."""
    view = ToolView(lambda: index, mode=mode, initial=names, page_size=page_size)
    try:
        for name in names:
            index.get_schema(name)
    finally:
        view.close()


def plan_mcp_tool_profile(mode: str = "full", *, names: Iterable[str] = (), page_size: int = 50,
                          read_only: bool | None = None) -> dict[str, Any]:
    """Preview validated stdio arguments; never start a server or alter existing session settings."""
    # pylint: disable-next=import-outside-toplevel  # reason: avoid a registry/type import cycle
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    readonly = read_only_env_flag() if read_only is None else bool(read_only)
    index = ToolIndex(build_default_tool_registry(read_only=readonly))
    validate_tool_profile(index, mode, names, page_size)
    arguments = ["je_auto_control_mcp", "--tool-mode", mode, "--tool-page-size", str(page_size)]
    if names:
        arguments.extend(["--tool-profile", ",".join(names)])
    if readonly:
        arguments.append("--read-only")
    return {"mode": mode, "names": list(names), "page_size": page_size, "read_only": readonly,
            "stdio_arguments": arguments}
