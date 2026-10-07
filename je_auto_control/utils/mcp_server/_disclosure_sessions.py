"""Connection-owned disclosure views, context leases and transport notification lookup."""
from __future__ import annotations

from collections.abc import Hashable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
import threading
from typing import Callable, Iterator, Sequence, cast

from je_auto_control.utils.mcp_server.discovery import ToolIndex
from je_auto_control.utils.mcp_server.disclosure import CORE_TOOLS, DisclosureMode, ToolDisclosureError, ToolView

NotificationSender = Callable[[str, dict[str, object]], None]


@dataclass(frozen=True)
class DisclosureSettings:
    """Immutable deployment settings; full without an explicit page size preserves legacy lists."""
    mode: DisclosureMode = 'full'
    profile: tuple[str, ...] = ()
    page_size: int | None = None


def environment_settings() -> DisclosureSettings:
    """Read explicit deployment mode/profile/page size, refusing malformed values."""
    mode = os.environ.get('JE_AUTOCONTROL_MCP_TOOL_MODE', 'full').strip().lower()
    if mode not in ('full', 'progressive', 'static'):
        raise ToolDisclosureError('tool mode must be full, progressive or static')
    profile = tuple(name.strip() for name in os.environ.get('JE_AUTOCONTROL_MCP_TOOL_PROFILE', '').split(',')
                    if name.strip())
    raw_size = os.environ.get('JE_AUTOCONTROL_MCP_TOOL_PAGE_SIZE')
    try:
        page_size = int(raw_size) if raw_size is not None else None
    except ValueError as error:
        raise ToolDisclosureError('tool page size must be an integer') from error
    return DisclosureSettings(cast(DisclosureMode, mode), profile, page_size)


class ToolSessions:
    """Own each HTTP/stdio view and preserve the accepted scope through late worker completion."""

    def __init__(self, index: Callable[[], ToolIndex], notify: Callable[[Hashable | None], None]) -> None:
        self._index = index
        self._notify = notify
        self._lock = threading.Lock()
        self._views: dict[Hashable | None, ToolView] = {}
        self._scope: ContextVar[ToolView | None] = ContextVar(f'mcp_tool_view_{id(self)}', default=None)
        self._lookup: Callable[[Hashable | None], NotificationSender | None] | None = None
        self.settings = environment_settings()
        self._validate(self.settings)

    def _validate(self, settings: DisclosureSettings) -> None:
        check = ToolView(self._index, mode=settings.mode, profile=settings.profile, page_size=settings.page_size)
        check.close()
        if settings.profile:
            index = self._index()
            for name in settings.profile:
                index.get_schema(name)

    def configure(self, mode: DisclosureMode, *, profile: Sequence[str] = (), page_size: int | None = None) -> None:
        """Configure before serving clients; active views cannot silently change deployment policy."""
        # ToolView validates a Sequence before converting it; strings must not turn into character profiles.
        check = ToolView(self._index, mode=mode, profile=profile, page_size=page_size)
        check.close()
        settings = DisclosureSettings(mode, tuple(profile), page_size)
        self._validate(settings)
        with self._lock:
            if self._views:
                raise ToolDisclosureError('configure disclosure before opening client views')
            self.settings = settings

    def _get(self, key: Hashable | None) -> ToolView:
        with self._lock:
            view = self._views.get(key)
            if view is None:
                settings = self.settings
                view = ToolView(self._index, mode=settings.mode, profile=settings.profile, page_size=settings.page_size,
                                notify=lambda: self._notify(key))
                self._views[key] = view
            return view

    @contextmanager
    def scope(self, key: Hashable | None) -> Iterator[None]:
        """Lease the exact view accepted for this request, even if the session is later dropped."""
        view = self._get(key)
        token = self._scope.set(view)
        try:
            yield
        finally:
            self._scope.reset(token)

    def current(self, *, stateless: bool = False) -> ToolView:
        """Return the leased owner; stateless requests get immutable deployment availability."""
        if stateless:
            settings = self.settings
            mode: DisclosureMode = 'full' if settings.mode == 'full' else 'static'
            return ToolView(self._index, mode=mode, profile=settings.profile)
        return self._scope.get() or self._get(None)

    def list_tools(self, cursor: str | None, *, stateless: bool = False) -> dict[str, object]:
        """Preserve default full wire shape; stable cursors are scoped to stateful sessions."""
        view = self.current(stateless=stateless)
        if stateless:
            if cursor is not None:
                raise ToolDisclosureError('stateless listing has no session cursor; use static/full profile')
            index = self._index()
            selected = set(self.settings.profile) | CORE_TOOLS
            names = index.authorized_names()
            return {'tools': [index.get_schema(name).to_dict() for name in names
                              if self.settings.mode == 'full' or name in selected]}
        page = view.list_page(cursor)
        if self.settings.mode == 'full' and self.settings.page_size is None:
            return {'tools': [tool.to_dict() for tool in page.tools]}
        return page.to_dict()

    def forget(self, key: Hashable | None) -> None:
        """Close and remove an owner; accepted context leases retain only a closed view."""
        with self._lock:
            view = self._views.pop(key, None)
        if view is not None:
            view.close()

    def close(self) -> None:
        """Revoke all owned views after a transport is stopped."""
        with self._lock:
            views = list(self._views.values())
            self._views.clear()
        for view in views:
            view.close()

    @property
    def view_count(self) -> int:
        """Number of active connection owners, excluding ephemeral stateless views."""
        with self._lock:
            return len(self._views)

    def set_notifier_lookup(self, lookup: Callable[[Hashable | None], NotificationSender | None]) -> None:
        """Install a metadata-only lookup for live standing HTTP streams."""
        self._lookup = lookup

    def notifier(self, key: Hashable | None) -> NotificationSender | None:
        """Resolve a currently live stream without retaining transient POST writers."""
        return self._lookup(key) if self._lookup is not None else None

    def notify_registry(self, exclude: Hashable | None) -> None:
        """Notify other stateful HTTP owners; stdio/current-request notifications use the existing path."""
        with self._lock:
            keys = [key for key in self._views if key is not None and key != exclude]
        for key in keys:
            self._notify(key)
