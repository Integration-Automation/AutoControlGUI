"""Connection-scoped state of the MCP server: who this thread is serving.

The stdio transport has exactly one peer, so a server-wide default is right
for it; an HTTP transport has many, and each request runs on its own thread.
Keeping the notifier, the writer, the concurrency switch and the peer's
identity in thread-local storage is what stops one client's progress
notifications from being emitted down another client's socket, and what lets
client capabilities, active calls and the tool view of a progressive session
(:mod:`.disclosure`) be scoped to one peer and released when it goes away.
"""
import contextlib
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, Optional

_Notifier = Callable[[str, Dict[str, Any]], None]
_Writer = Callable[[str], None]


class ConnectionStateMixin:
    """Per-peer state, mixed into :class:`MCPServer`.

    Requires the host to provide ``_local`` (thread-local storage), the
    ``_default_*`` slots, ``_client_caps_by_conn`` with ``_caps_lock``,
    ``_active_calls`` with ``_calls_lock``, ``_stateless_request``,
    ``_end_listeners`` and ``disclosure``.
    """

    if TYPE_CHECKING:
        _local: Any
        _default_notifier: Optional[Callable[[str, Dict[str, Any]], None]]
        _default_writer: Optional[Callable[[str], None]]
        _default_concurrent_tools: bool
        _default_client_capabilities: Dict[str, Any]
        _client_caps_by_conn: Dict[Any, Dict[str, Any]]
        _caps_lock: threading.Lock
        _active_calls: Dict[Any, Any]
        _calls_lock: threading.Lock
        disclosure: Any

        @property
        def _stateless_request(self) -> Any:
            """The 2026-07-28 request being served on this thread, if any."""

        def _end_listeners(self, which: Callable[[Any], bool], graceful: bool) -> None:
            """End every subscription whose connection id satisfies ``which``."""

    # --- thread-scoped accessors --------------------------------------------
    #
    # Each property prefers a value set for the current thread (one HTTP
    # request = one thread) and falls back to the server-wide default that
    # stdio and set_notifier() use. A plain POST therefore sees *no* notifier
    # rather than inheriting whichever SSE connection happens to be open —
    # correct, since a plain POST has no stream to deliver notifications on.

    @property
    def _notifier(self) -> Optional[Callable[[str, Dict[str, Any]], None]]:
        return getattr(self._local, "notifier", None) or self._default_notifier

    @_notifier.setter
    def _notifier(self, value: Optional[_Notifier]) -> None:
        self._default_notifier = value

    @property
    def _writer(self) -> Optional[Callable[[str], None]]:
        return getattr(self._local, "writer", None) or self._default_writer

    @_writer.setter
    def _writer(self, value: Optional[_Writer]) -> None:
        self._default_writer = value

    @property
    def _concurrent_tools(self) -> bool:
        scoped = getattr(self._local, "concurrent_tools", None)
        if scoped is None:
            return self._default_concurrent_tools
        return scoped

    @_concurrent_tools.setter
    def _concurrent_tools(self, value: object) -> None:
        self._default_concurrent_tools = bool(value)

    @property
    def _connection_id(self) -> Any:
        """Identity of the peer served on this thread (None for stdio)."""
        return getattr(self._local, "connection_id", None)

    @property
    def _client_capabilities(self) -> Dict[str, Any]:
        """Capabilities advertised by the peer served on this thread."""
        if self._stateless_request is not None:
            return self._stateless_request.capabilities
        conn = self._connection_id
        if conn is None:
            return self._default_client_capabilities
        with self._caps_lock:
            return self._client_caps_by_conn.get(conn, {})

    @_client_capabilities.setter
    def _client_capabilities(self, value: Dict[str, Any]) -> None:
        conn = self._connection_id
        if conn is None:
            self._default_client_capabilities = value
            return
        with self._caps_lock:
            self._client_caps_by_conn[conn] = value

    @contextlib.contextmanager
    def connection_scope(self, *, notifier: Optional[_Notifier] = None,
                         writer: Optional[_Writer] = None,
                         concurrent_tools: Optional[bool] = None,
                         connection_id: Any = None) -> Iterator[Any]:
        """Bind notifier/writer/concurrency/identity to the calling thread only.

        Transports that serve more than one peer must wrap each request in
        this. Previously they swapped the attributes on the shared server, so
        any concurrent request bound to the wrong peer's socket. ``connection_id``
        scopes active-call slots and client capabilities per peer.
        """
        prior = (getattr(self._local, "notifier", None),
                 getattr(self._local, "writer", None),
                 getattr(self._local, "concurrent_tools", None),
                 getattr(self._local, "connection_id", None))
        self._local.notifier = notifier
        self._local.writer = writer
        self._local.concurrent_tools = concurrent_tools
        self._local.connection_id = connection_id
        try:
            yield self
        finally:
            (self._local.notifier, self._local.writer,
             self._local.concurrent_tools, self._local.connection_id) = prior

    def forget_connection(self, connection_id: Any) -> None:
        """Drop per-connection state when a transport connection closes.

        HTTP connections are transient; without this their capabilities and
        any stray active-call contexts would accumulate for the server's life.
        """
        if connection_id is None:
            return
        with self._caps_lock:
            self._client_caps_by_conn.pop(connection_id, None)
        self._end_listeners(lambda conn: conn == connection_id, graceful=False)
        self.disclosure.forget(connection_id)
        with self._calls_lock:
            stale = [key for key in self._active_calls
                     if isinstance(key, tuple) and key[0] == connection_id]
            for key in stale:
                self._active_calls.pop(key, None)
