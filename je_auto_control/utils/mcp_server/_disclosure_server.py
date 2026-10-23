"""Bind tool availability to transport lifetimes while retaining the existing dispatcher gates."""
from __future__ import annotations

from contextlib import contextmanager
import os
import threading
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator

from je_auto_control.utils.mcp_server.discovery import ToolCatalogMixin, ToolDiscoveryError
from je_auto_control.utils.mcp_server.disclosure import ToolView, validate_tool_profile
from je_auto_control.utils.mcp_server._protocol import _MCPError
from je_auto_control.utils.mcp_server.tools._base import read_only_env_flag
from je_auto_control.utils.rbac.authorization import AuthorizationContext, current_authorization
from je_auto_control.utils.rbac.deferred import DeferredAuthorization


class DisclosureServerMixin(ToolCatalogMixin):
    """Own one disclosure view per session; stale in-flight callbacks retain closed views."""

    if TYPE_CHECKING:
        _agent_session: str
        _connection_id: Any
        _stateless_request: Any
        _notify_tools_list_changed: Callable[..., None]

    def _init_tool_disclosure(self) -> None:
        self._disclosure_lock = threading.RLock()
        self._disclosure_views: dict[Any, ToolView] = {}
        self._disclosure_mode = "full"
        self._disclosure_initial: tuple[str, ...] = ()
        self._disclosure_page_size = 50
        self._disclosure_closed = False
        self._read_only_tools = read_only_env_flag()
        initial = tuple(filter(None, (item.strip() for item in os.environ.get(
            "JE_AUTOCONTROL_MCP_TOOL_PROFILE", "").split(","))))
        self.configure_tool_disclosure(os.environ.get("JE_AUTOCONTROL_MCP_DISCLOSURE", "full"), names=initial)

    def configure_tool_disclosure(self, mode: str, *, names: Iterable[str] = (), page_size: int = 50,
                                  read_only: bool | None = None) -> None:
        """Configure an inert host-owned full/progressive/static profile and retire previous session views."""
        if read_only is not None and not isinstance(read_only, bool):
            raise ToolDiscoveryError("read_only must be boolean")
        readonly = self._read_only_tools if read_only is None else read_only
        validate_tool_profile(self._filtered_tool_index(readonly), mode, names, page_size)
        with self._disclosure_lock:
            for view in self._disclosure_views.values():
                view.close()
            self._disclosure_views.clear()
            self._disclosure_mode, self._disclosure_initial = mode, tuple(names)
            self._disclosure_page_size = page_size
            if read_only is not None:
                self._read_only_tools = read_only
        self._notify_tools_list_changed()

    def tool_disclosure_configuration(self) -> dict[str, Any]:
        """Inspect this inert host configuration; session tools never gain authority from these settings."""
        with self._disclosure_lock:
            return {"mode": self._disclosure_mode, "names": list(self._disclosure_initial),
                    "page_size": self._disclosure_page_size, "read_only": self._read_only_tools}

    @contextmanager
    def _discovery_authority(self) -> Iterator[None]:
        caller = current_authorization()
        if caller is None:
            caller = AuthorizationContext(f"mcp:{self._agent_session}:{self._connection_id}", "operator")
        with DeferredAuthorization(caller).context_scope():
            yield

    def _new_tool_view(self, stateless: bool) -> ToolView:
        mode = self._disclosure_mode
        if stateless and mode == "progressive":
            mode = "static"
        connection = self._connection_id
        return ToolView(self.tool_index, mode=mode, initial=self._disclosure_initial,
                        page_size=self._disclosure_page_size,
                        changed=lambda: self._notify_tools_list_changed(connection_id=connection))

    def _session_tool_view(self) -> ToolView:
        with self._disclosure_lock:
            if self._disclosure_closed:
                raise ToolDiscoveryError("tool disclosure is closed")
            if self._stateless_request is not None:
                return self._new_tool_view(True)
            connection = self._connection_id
            if connection not in self._disclosure_views:
                if len(self._disclosure_views) >= 1024:
                    raise ToolDiscoveryError("tool disclosure session limit reached")
                self._disclosure_views[connection] = self._new_tool_view(False)
            return self._disclosure_views[connection]

    def _call_tool_catalog(self, view: ToolView | None = None) -> Callable[[], ToolView]:
        view = view if view is not None else self._session_tool_view()
        return lambda: view

    def _require_disclosed_tool(self, name: str, view: ToolView | None = None) -> None:
        if self._disclosure_mode == "full" and not self._read_only_tools:
            return
        try:
            with self._discovery_authority():
                (view if view is not None else self._session_tool_view()).require_available(name)
        except ToolDiscoveryError as error:
            raise _MCPError(-32602, str(error)) from error

    def _handle_tools_list(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """List one availability snapshot, preserving full-mode and stateless response compatibility."""
        try:
            with self._discovery_authority():
                view = self._session_tool_view()
                page = view.list_page((params or {}).get("cursor"))
                if self._stateless_request is not None:
                    while "nextCursor" in page:
                        following = view.list_page(page.pop("nextCursor"))
                        page["tools"].extend(following["tools"])
                        if "nextCursor" in following:
                            page["nextCursor"] = following["nextCursor"]
                result: dict[str, Any] = {"tools": page["tools"]}
                if self._disclosure_mode != "full":
                    result["_meta"] = {"autocontrol/snapshot": page["snapshot_id"]}
                if "nextCursor" in page:
                    result["nextCursor"] = page["nextCursor"]
                return result
        except ToolDiscoveryError as error:
            raise _MCPError(-32602, str(error)) from error

    def _forget_tool_view(self, connection: Any) -> None:
        with self._disclosure_lock:
            view = self._disclosure_views.pop(connection, None)
        if view is not None:
            view.close()

    def _close_tool_views(self) -> None:
        with self._disclosure_lock:
            self._disclosure_closed = True
            for view in self._disclosure_views.values():
                view.close()
            self._disclosure_views.clear()
