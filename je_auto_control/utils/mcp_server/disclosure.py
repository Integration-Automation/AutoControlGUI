"""Which tools a session is offered: all of them, or a small core that grows.

``tools/list`` in the default **full** mode answers with every registered
tool, as it always has. Two other modes exist for clients that should not
carry several hundred schemas they will never use:

* **progressive** -- a session starts with the core tools of
  :mod:`._core_tools` (search, schema, enable, disable, state) and enables
  what it needs. The enabled set belongs to one session: an HTTP
  ``Mcp-Session-Id`` (or, for a client that ignores the header, its
  connection), and the one implicit session of a stdio server. Enabling
  sends that session ``notifications/tools/list_changed``.
* **static** -- ``tools/list`` is a fixed profile and nothing can be enabled,
  for a client that reads the list once and never again. A 2026-07-28 request
  is served this way in progressive mode too: that revision has no session
  for an enabled set to live in.

Disclosure changes what is *offered*, never what is *allowed*. The registry
stays the only source of tools; a view is a set of names filtered through it
on every use, so a tool a plugin removed, the caller's role does not grant
or read-only mode rules out is gone from the view whatever the session
remembers. A call still passes every existing gate in
``MCPServer._prepare_tool_call`` -- role, schema, path roots, rate limit,
confirmation -- and :meth:`ToolDisclosure.require_available` only adds one
more refusal in front of them.

Read-only is enforced here for every mode, when a list is answered and when
a call arrives, not only when the default registry is built: a mutating tool
registered on a running read-only server (a plugin) is neither listed nor
run, in full mode as in the other two.

``tools/list`` is paged in these two modes. A cursor names a snapshot of the
view taken when its first page was requested, so later pages come from that
same list even if a plugin changed the registry in between; a cursor whose
snapshot is no longer kept is refused instead of paging a different list.
"""
import base64
import hashlib
import hmac
import os
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple,
)

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server._authz import visible_tools
from je_auto_control.utils.mcp_server._protocol import _MCPError
from je_auto_control.utils.mcp_server.discovery import ToolIndex, category_of
from je_auto_control.utils.mcp_server.tools import COMMON_TOOL_NAMES, MCPTool
from je_auto_control.utils.mcp_server.tools._base import read_only_env_flag
from je_auto_control.utils.rbac.authorization import current_authorization

if TYPE_CHECKING:
    from je_auto_control.utils.mcp_server.server import MCPServer

#: ``full`` (default), ``progressive`` or ``static``.
MODE_ENV = "JE_AUTOCONTROL_MCP_TOOL_MODE"
#: Comma-separated tool names and ``category:<name>`` entries.
PROFILE_ENV = "JE_AUTOCONTROL_MCP_TOOL_PROFILE"
#: ``_meta`` key of a paged ``tools/list`` result: the snapshot it is a page of.
SNAPSHOT_META = "io.github.integration-automation/toolSnapshot"
#: The static profile when none is configured: the tools behind the aliases.
DEFAULT_PROFILE: Tuple[str, ...] = COMMON_TOOL_NAMES
DEFAULT_PAGE_SIZE = 100
#: Entries one enable / disable call may name.
MAX_NAMES_PER_CALL = 100
CATEGORY_PREFIX = "category:"
_MAX_NAME_CHARS = 200
#: Views kept at once. HTTP sessions are capped far below this; it bounds a leak.
_MAX_VIEWS = 1024
_MAX_CACHED_CALLERS = 16
_LIST_CHANGED = "notifications/tools/list_changed"
_SEND_ERRORS = (OSError, RuntimeError, ValueError)

SEARCH_TOOL = "ac_tools_search"
SCHEMA_TOOL = "ac_tools_schema"
ENABLE_TOOL = "ac_tools_enable"
DISABLE_TOOL = "ac_tools_disable"
STATE_TOOL = "ac_tools_state"
#: What a progressive session starts with, in the order it is listed.
CORE_TOOL_NAMES: Tuple[str, ...] = (
    SEARCH_TOOL, SCHEMA_TOOL, ENABLE_TOOL, DISABLE_TOOL, STATE_TOOL)


class ToolDisclosureError(AutoControlException, ValueError):
    """A disclosure request that cannot be honoured as asked."""


class ToolMode(str, Enum):
    """How much of the registry ``tools/list`` offers."""

    FULL = "full"
    PROGRESSIVE = "progressive"
    STATIC = "static"


def resolve_mode(explicit: str | ToolMode | None,
                 environ: Optional[Mapping[str, str]] = None) -> ToolMode:
    """The mode ``explicit`` names, else the one ``JE_AUTOCONTROL_MCP_TOOL_MODE`` does.

    Unset or blank means full. A value that is none of the three raises
    :class:`ToolDisclosureError`: a typo must not quietly start a server
    that offers every tool.
    """
    if explicit is not None:
        raw = explicit
    else:
        raw = (os.environ if environ is None else environ).get(MODE_ENV, "")
    if isinstance(raw, ToolMode):
        return raw
    text = str(raw).strip().lower()
    if not text:
        return ToolMode.FULL
    try:
        return ToolMode(text)
    except ValueError as error:
        known = ", ".join(mode.value for mode in ToolMode)
        raise ToolDisclosureError(f"unknown MCP tool mode {raw!r}; expected one of: {known}") from error


def profile_from_env(environ: Optional[Mapping[str, str]] = None) -> Optional[Tuple[str, ...]]:
    """The entries of ``JE_AUTOCONTROL_MCP_TOOL_PROFILE``; ``None`` when unset."""
    raw = (os.environ if environ is None else environ).get(PROFILE_ENV, "")
    entries = tuple(part.strip() for part in raw.split(",") if part.strip())
    return entries or None


@dataclass(frozen=True)
class Catalog:
    """The tools one caller may use at one registry revision, in registry order."""

    tools: Mapping[str, MCPTool]
    revision: int
    #: The RBAC role the tools were filtered for; ``None`` outside RBAC.
    caller: Optional[str] = None

    def expand(self, entry: str) -> List[str]:
        """The tool names ``entry`` stands for; empty when it names nothing here."""
        if entry.startswith(CATEGORY_PREFIX):
            wanted = entry[len(CATEGORY_PREFIX):]
            return [name for name, tool in self.tools.items() if category_of(tool) == wanted]
        return [entry] if entry in self.tools else []


@dataclass(frozen=True)
class DisclosureResult:
    """What one enable or disable call did to a session's view."""

    enabled: Tuple[str, ...] = ()
    already_enabled: Tuple[str, ...] = ()
    disabled: Tuple[str, ...] = ()
    #: Entries that name nothing this caller may enable (or has enabled).
    unavailable: Tuple[str, ...] = ()
    visible_count: int = 0
    #: Whether ``notifications/tools/list_changed`` went to the session.
    list_changed_sent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON shape the enable and disable tools reply with."""
        return {
            "enabled": list(self.enabled), "already_enabled": list(self.already_enabled),
            "disabled": list(self.disabled), "unavailable": list(self.unavailable),
            "visible_count": self.visible_count,
            "list_changed_sent": self.list_changed_sent,
        }


@dataclass(frozen=True)
class ToolPage:
    """One page of a session's ``tools/list``."""

    tools: Tuple[MCPTool, ...]
    #: Opaque; ``None`` on the last page.
    next_cursor: Optional[str]
    #: Identifies the list this is a page of; every page of one list shares it.
    snapshot_id: str

    def to_result(self) -> Dict[str, Any]:
        """Return the ``tools/list`` result for this page."""
        result: Dict[str, Any] = {"tools": [tool.to_descriptor() for tool in self.tools]}
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        result["_meta"] = {SNAPSHOT_META: self.snapshot_id}
        return result


@dataclass(frozen=True)
class _Snapshot:
    tools: Tuple[MCPTool, ...]
    caller: Optional[str]


def _checked_names(names: Any) -> List[str]:
    """``names`` as a de-duplicated list of entries, or :class:`ToolDisclosureError`."""
    if isinstance(names, (str, bytes)) or not isinstance(names, Sequence):
        raise ToolDisclosureError("names must be a list of tool names")
    if len(names) > MAX_NAMES_PER_CALL:
        raise ToolDisclosureError(f"at most {MAX_NAMES_PER_CALL} names per call")
    for name in names:
        if not isinstance(name, str) or not name or len(name) > _MAX_NAME_CHARS:
            raise ToolDisclosureError("every name must be a non-empty string")
    return list(dict.fromkeys(names))


class ToolView:
    """One session's tools: what is pinned for it plus what it enabled.

    ``catalog`` returns the tools the current caller may use right now. The
    view only ever holds names, so everything it reports is the intersection
    of those names with that catalog at the moment of asking. ``fixed``
    makes a static profile: its pinned entries are the whole view.
    """

    #: Paged lists remembered per view; the oldest is dropped beyond this.
    max_snapshots = 8

    def __init__(self, catalog: Callable[[], Catalog], *,
                 pinned: Sequence[str] = (),
                 page_size: Callable[[], int] = lambda: DEFAULT_PAGE_SIZE,
                 on_change: Optional[Callable[[], bool]] = None,
                 fixed: bool = False) -> None:
        self._catalog = catalog
        self._pinned = tuple(pinned)
        self._page_size = page_size
        self._on_change = on_change
        self._fixed = bool(fixed)
        self._enabled: Dict[str, None] = {}
        self._revision = 0
        self._snapshots: "OrderedDict[str, _Snapshot]" = OrderedDict()
        self._secret = secrets.token_bytes(16)
        self._lock = threading.Lock()

    @property
    def fixed(self) -> bool:
        """Whether this is a static profile, which nothing can be enabled in."""
        return self._fixed

    @property
    def visible_names(self) -> Tuple[str, ...]:
        """Names of the tools this view offers the current caller, in list order."""
        return tuple(tool.name for tool in self.visible_tools())

    @property
    def enabled_names(self) -> Tuple[str, ...]:
        """The names this session enabled, whether or not they are still offered."""
        with self._lock:
            return tuple(self._enabled)

    def visible_tools(self) -> Tuple[MCPTool, ...]:
        """The tools this view offers the current caller: pinned first, then enabled."""
        return self._visible(self._catalog())

    def allows(self, name: str) -> bool:
        """Whether ``name`` is offered to the current caller by this view."""
        catalog = self._catalog()
        if name not in catalog.tools:
            return False
        with self._lock:
            if name in self._enabled:
                return True
        return name in self._pinned_names(catalog)

    def enable(self, names: Sequence[str]) -> DisclosureResult:
        """Add tools to this session's list; ``category:<name>`` adds a whole category.

        An entry that names nothing the current caller may use is reported
        as unavailable, without saying whether it exists. Raises
        :class:`ToolDisclosureError` for malformed input or a static profile.
        """
        entries = _checked_names(names)
        self._require_mutable()
        catalog = self._catalog()
        pinned = set(self._pinned_names(catalog))
        enabled: List[str] = []
        already: List[str] = []
        unavailable: List[str] = []
        with self._lock:
            for entry in entries:
                targets = catalog.expand(entry)
                if not targets:
                    unavailable.append(entry)
                for name in targets:
                    if name in pinned or name in self._enabled:
                        already.append(name)
                    else:
                        self._enabled[name] = None
                        enabled.append(name)
            if enabled:
                self._revision += 1
        return DisclosureResult(
            enabled=tuple(enabled), already_enabled=tuple(already),
            unavailable=tuple(unavailable), visible_count=len(self._visible(catalog)),
            list_changed_sent=self._announce(bool(enabled)),
        )

    def disable(self, names: Sequence[str]) -> DisclosureResult:
        """Remove tools this session enabled; pinned tools cannot be removed."""
        entries = _checked_names(names)
        self._require_mutable()
        catalog = self._catalog()
        disabled: List[str] = []
        unavailable: List[str] = []
        with self._lock:
            for entry in entries:
                targets = [name for name in (catalog.expand(entry) or [entry])
                           if name in self._enabled]
                if not targets:
                    unavailable.append(entry)
                for name in targets:
                    del self._enabled[name]
                    disabled.append(name)
            if disabled:
                self._revision += 1
        return DisclosureResult(
            disabled=tuple(disabled), unavailable=tuple(unavailable),
            visible_count=len(self._visible(catalog)),
            list_changed_sent=self._announce(bool(disabled)),
        )

    def forget_tool(self, name: str) -> None:
        """Drop ``name`` from the enabled set: the registry no longer has it.

        Without this a tool registered later under the same name would be
        enabled in a session that never asked for *that* tool.
        """
        with self._lock:
            if self._enabled.pop(name, 0) is None:
                self._revision += 1

    def list_page(self, cursor: Optional[str]) -> ToolPage:
        """The first page of this view, or the page ``cursor`` continues.

        Raises :class:`ToolDisclosureError` for a cursor that is malformed,
        belongs to another session or caller, or names a snapshot this view
        no longer keeps.
        """
        catalog = self._catalog()
        size = max(1, int(self._page_size()))
        if cursor is None:
            tools = self._visible(catalog)
            snapshot_id = self._snapshot_id(catalog)
            if len(tools) > size:
                self._remember(snapshot_id, _Snapshot(tools, catalog.caller))
            return self._page(snapshot_id, tools, 0, size)
        snapshot_id, offset = self._decode(cursor)
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
        if (snapshot is None or snapshot.caller != catalog.caller
                or not 0 < offset < len(snapshot.tools)):
            raise ToolDisclosureError(
                "stale or unknown cursor; request tools/list again without one")
        return self._page(snapshot_id, snapshot.tools, offset, size)

    # --- internals ----------------------------------------------------------------

    def _require_mutable(self) -> None:
        if self._fixed:
            raise ToolDisclosureError("this tool list is a static profile; nothing can be enabled")

    def _announce(self, changed: bool) -> bool:
        if not changed or self._on_change is None:
            return False
        return bool(self._on_change())

    def _pinned_names(self, catalog: Catalog) -> List[str]:
        names: Dict[str, None] = {}
        for entry in self._pinned:
            names.update(dict.fromkeys(catalog.expand(entry)))
        return list(names)

    def _visible(self, catalog: Catalog) -> Tuple[MCPTool, ...]:
        pinned = self._pinned_names(catalog)
        with self._lock:
            enabled = set(self._enabled) - set(pinned)
        tools = catalog.tools
        return tuple([tools[name] for name in pinned]
                     + [tool for name, tool in tools.items() if name in enabled])

    def _snapshot_id(self, catalog: Catalog) -> str:
        with self._lock:
            state = f"{catalog.revision}|{catalog.caller}|{self._revision}"
        return self._mac(state)

    def _mac(self, text: str) -> str:
        return hmac.new(self._secret, text.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    def _remember(self, snapshot_id: str, snapshot: _Snapshot) -> None:
        with self._lock:
            self._snapshots[snapshot_id] = snapshot
            self._snapshots.move_to_end(snapshot_id)
            while len(self._snapshots) > self.max_snapshots:
                self._snapshots.popitem(last=False)

    def _page(self, snapshot_id: str, tools: Tuple[MCPTool, ...],
              offset: int, size: int) -> ToolPage:
        end = offset + size
        cursor = self._encode(snapshot_id, end) if end < len(tools) else None
        return ToolPage(tools=tools[offset:end], next_cursor=cursor, snapshot_id=snapshot_id)

    def _encode(self, snapshot_id: str, offset: int) -> str:
        body = f"{snapshot_id}.{offset}"
        token = f"{body}.{self._mac(body)}".encode("ascii")
        return base64.urlsafe_b64encode(token).decode("ascii").rstrip("=")

    def _decode(self, cursor: str) -> Tuple[str, int]:
        """``(snapshot id, offset)`` of a cursor this view issued."""
        malformed = ToolDisclosureError("malformed cursor")
        if not isinstance(cursor, str) or not cursor or len(cursor) > 4 * _MAX_NAME_CHARS:
            raise malformed
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            text = base64.b64decode(padded, altchars=b"-_", validate=True).decode("ascii")
        except ValueError as error:  # binascii.Error and UnicodeDecodeError are both ValueErrors
            raise malformed from error
        snapshot_id, _, rest = text.partition(".")
        number, _, mac = rest.partition(".")
        if not number.isdigit() or not hmac.compare_digest(
                mac, self._mac(f"{snapshot_id}.{number}")):
            raise malformed
        return snapshot_id, int(number)


class ToolDisclosure:
    """The tool mode of one :class:`MCPServer` and the views of its sessions.

    ``mode``, ``read_only`` and ``profile`` default to what the environment
    says (``JE_AUTOCONTROL_MCP_TOOL_MODE``, ``JE_AUTOCONTROL_MCP_READONLY``,
    ``JE_AUTOCONTROL_MCP_TOOL_PROFILE``). ``page_size`` may be reassigned.
    """

    def __init__(self, server: "MCPServer",
                 mode: str | ToolMode | None = None, *,
                 read_only: Optional[bool] = None,
                 profile: Optional[Sequence[str]] = None,
                 page_size: int = DEFAULT_PAGE_SIZE) -> None:
        self._server = server
        self.mode = resolve_mode(mode)
        self.read_only = read_only_env_flag() if read_only is None else bool(read_only)
        configured = profile_from_env() if profile is None else tuple(profile)
        #: The configured profile; ``None`` when the default one applies.
        self.profile: Optional[Tuple[str, ...]] = configured
        self.page_size = page_size
        self._revision = 0
        self._lock = threading.Lock()
        self._views: "OrderedDict[Any, ToolView]" = OrderedDict()
        self._catalogs: Dict[Optional[str], Catalog] = {}
        self._indexes: Dict[Optional[str], ToolIndex] = {}
        self._static_view = ToolView(
            self.catalog, pinned=DEFAULT_PROFILE if configured is None else configured,
            page_size=self._current_page_size, fixed=True)

    @property
    def argument_policy(self) -> Any:
        """The server's path roots and ``env://`` allowlist, which calls are held to."""
        return self._server.argument_policy

    @property
    def session_count(self) -> int:
        """How many sessions currently hold a view."""
        with self._lock:
            return len(self._views)

    # --- the registry, as the current caller may use it -----------------------------

    def catalog(self) -> Catalog:
        """The tools the current caller may use, read from the live registry."""
        caller = current_authorization()
        role = caller.role if caller is not None else None
        with self._lock:
            revision = self._revision
            cached = self._catalogs.get(role)
        if cached is not None and cached.revision == revision:
            return cached
        with self._server._tools_lock:
            registered = list(self._server._tools.values())
        allowed = visible_tools(registered)
        if self.read_only:
            allowed = [tool for tool in allowed if tool.annotations.read_only]
        catalog = Catalog({tool.name: tool for tool in allowed}, revision, role)
        with self._lock:
            if len(self._catalogs) >= _MAX_CACHED_CALLERS:
                self._catalogs.clear()
            self._catalogs[role] = catalog
        return catalog

    def index(self) -> ToolIndex:
        """The search index over :meth:`catalog`, rebuilt when the registry changes."""
        catalog = self.catalog()
        with self._lock:
            cached = self._indexes.get(catalog.caller)
        if cached is not None and cached.version == catalog.revision:
            return cached
        index = ToolIndex((tool for name, tool in catalog.tools.items()
                           if name not in CORE_TOOL_NAMES), version=catalog.revision)
        with self._lock:
            if len(self._indexes) >= _MAX_CACHED_CALLERS:
                self._indexes.clear()
            self._indexes[catalog.caller] = index
        return index

    def check_name(self, name: str) -> None:
        """Refuse to register or remove a tool under a core tool's name."""
        if self.mode is ToolMode.PROGRESSIVE and name in CORE_TOOL_NAMES:
            raise ToolDisclosureError(f"{name!r} is a core tool of the progressive mode")

    def registry_changed(self, removed: Optional[str] = None) -> None:
        """Note that the registry changed; ``removed`` is forgotten by every session."""
        with self._lock:
            self._revision += 1
            views = list(self._views.values())
        if removed is not None:
            for view in views:
                view.forget_tool(removed)

    # --- sessions ------------------------------------------------------------------

    def view_for(self, connection_id: Any) -> ToolView:
        """The view of the session ``connection_id``; ``None`` is the stdio session."""
        with self._lock:
            view = self._views.get(connection_id)
            if view is not None:
                return view
            view = ToolView(self.catalog, pinned=CORE_TOOL_NAMES + (self.profile or ()),
                            page_size=self._current_page_size, on_change=self._announce)
            self._views[connection_id] = view
            while len(self._views) > _MAX_VIEWS:
                dropped, _view = self._views.popitem(last=False)
                autocontrol_logger.warning(
                    "MCP tool views exceeded %d; dropping the oldest (%r)", _MAX_VIEWS, dropped)
            return view

    def current_view(self) -> ToolView:
        """The view the request on this thread is served from."""
        if self.mode is not ToolMode.PROGRESSIVE or self._server._stateless_request is not None:
            return self._static_view
        return self.view_for(self._server._connection_id)

    def forget(self, connection_id: Any) -> None:
        """Release the view of a session that ended."""
        with self._lock:
            self._views.pop(connection_id, None)

    def initial_tools(self) -> List[MCPTool]:
        """What ``tools/list`` offers a session that has enabled nothing."""
        if self.mode is ToolMode.FULL:
            return self._full_list()
        return list(self.current_view().visible_tools())

    # --- the dispatcher's two questions ----------------------------------------------

    def handle_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Answer ``tools/list``: the whole registry in full mode, else one page."""
        if self.mode is ToolMode.FULL:
            return {"tools": [tool.to_descriptor() for tool in self._full_list()]}
        try:
            return self.current_view().list_page(params.get("cursor")).to_result()
        except ToolDisclosureError as error:
            raise _MCPError(-32602, f"Invalid params: {error}") from error

    def require_available(self, tool: MCPTool, arguments: Dict[str, Any]) -> None:
        """Refuse a call to a tool this server, or the session's view, does not offer.

        In full mode the only refusal is a mutating tool on a read-only
        server. This runs after the role check and before every other gate,
        and a refusal is recorded like a role one.
        """
        message = self._unavailable_reason(tool)
        if message is None:
            return
        self._server._audit.record(tool=tool.name, arguments=arguments, status="denied",
                                   duration_seconds=0.0, error_text=message)
        raise _MCPError(-32602, message)

    def _unavailable_reason(self, tool: MCPTool) -> Optional[str]:
        """Why ``tool`` cannot be called here; ``None`` when it can."""
        if self.mode is ToolMode.FULL:
            if self.read_only and not tool.annotations.read_only:
                return (f"Tool {tool.name!r} is not available: this server is read-only "
                        "and the tool is not marked read-only")
            return None
        view = self.current_view()
        if view.allows(tool.name):
            return None
        if not view.fixed and tool.name in self.catalog().tools:
            return (f"Tool {tool.name!r} is not enabled in this session; "
                    f"enable it with {ENABLE_TOOL} first")
        return f"Tool {tool.name!r} is not available in this session"

    def _full_list(self) -> List[MCPTool]:
        # Snapshot under the lock: PluginWatcher re-registers tools from its
        # own thread, and mutating the dict mid-iteration surfaced to the
        # client as "-32603 dictionary changed size during iteration".
        with self._server._tools_lock:
            tools = list(self._server._tools.values())
        if self.read_only:
            # Not only at build time: a plugin registers into a running server.
            tools = [tool for tool in tools if tool.annotations.read_only]
        return visible_tools(tools)

    def _current_page_size(self) -> int:
        return self.page_size

    def _announce(self) -> bool:
        """Tell the session being served that its list changed; ``False`` if it cannot hear."""
        notifier = self._server._unsolicited_notifier()
        if notifier is None:
            return False
        try:
            notifier(_LIST_CHANGED, {})
        except _SEND_ERRORS:
            autocontrol_logger.exception("MCP failed to send tools/list_changed")
            return False
        return True


__all__ = [
    "CATEGORY_PREFIX", "CORE_TOOL_NAMES", "Catalog", "DEFAULT_PAGE_SIZE", "DEFAULT_PROFILE",
    "DISABLE_TOOL", "DisclosureResult", "ENABLE_TOOL", "MAX_NAMES_PER_CALL", "MODE_ENV",
    "PROFILE_ENV", "SCHEMA_TOOL", "SEARCH_TOOL", "SNAPSHOT_META", "STATE_TOOL",
    "ToolDisclosure", "ToolDisclosureError", "ToolMode", "ToolPage", "ToolView",
    "profile_from_env", "resolve_mode",
]
