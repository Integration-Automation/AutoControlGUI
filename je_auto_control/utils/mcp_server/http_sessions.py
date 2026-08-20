"""MCP session identity for the HTTP transport.

The Streamable HTTP transport used to scope every peer on the identity of
its TCP connection. That is not what MCP means by a session: a client is
free to send ``initialize`` on one connection and ``tools/call`` on the
next, and an SSE response closes its connection after the final event. Any
state established at ``initialize`` — most importantly the ``elicitation``
capability the destructive-action confirmation gate depends on — was
therefore gone by the time it was needed.

This module holds the identity that outlives a connection: a registry of
``Mcp-Session-Id`` values, each owning the optional standing server-to-client
SSE stream opened by ``GET``. The dispatcher itself needs no changes — it
already scopes capabilities and active calls on an opaque ``connection_id``,
so a session id simply takes that slot.

Sessions are bounded in both directions: idle ones are swept, and the
registry never grows past ``max_sessions``. Whenever a session is dropped
the registry reports it through ``on_drop`` so the transport can release the
dispatcher state held under that id.
"""
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# MCP names the header in this casing; HTTP lookups are case-insensitive.
SESSION_HEADER = "Mcp-Session-Id"
# A session costs one dict entry plus at most one streaming thread, but an
# unbounded registry is still a memory target for an unauthenticated peer.
DEFAULT_MAX_SESSIONS = 128
# How long a session may go untouched before it is swept. Clients that keep a
# standing GET stream open touch it on every heartbeat, so this bounds only
# genuinely abandoned sessions.
DEFAULT_IDLE_TIMEOUT = 600.0
# Bytes of entropy in a session id. The spec asks for cryptographically
# secure and globally unique; 32 bytes is comfortably both.
_ID_ENTROPY_BYTES = 32


class HttpSession:
    """One MCP session: an identity, plus its optional outbound stream.

    The stream is the ``GET`` SSE channel the client may open to receive
    server-initiated traffic — progress notifications, and the
    ``elicitation/create`` request the confirmation gate sends. Without it
    the server has no way to ask the client anything between a request and
    its response, which is why a session with no stream still cannot be
    prompted.
    """

    def __init__(self, session_id: str, now: float) -> None:
        self.id = session_id
        self.created_at = now
        self.last_seen = now
        self.closed = threading.Event()
        self._lock = threading.Lock()
        self._stream_writer: Optional[Callable[[str], None]] = None

    @property
    def has_stream(self) -> bool:
        """True while a standing server-to-client SSE stream is attached."""
        with self._lock:
            return self._stream_writer is not None

    @property
    def stream_writer(self) -> Optional[Callable[[str], None]]:
        """The attached stream's emit callable, or ``None``."""
        with self._lock:
            return self._stream_writer

    def attach_stream(self, writer: Callable[[str], None]) -> bool:
        """Attach the standing stream; False when one is already attached.

        Refusing the second stream is deliberate. Two streams on one session
        would make "which socket does this elicitation go down" ambiguous,
        and the client cannot tell which one the server picked.
        """
        with self._lock:
            if self._stream_writer is not None:
                return False
            self._stream_writer = writer
            return True

    def detach_stream(self, writer: Callable[[str], None]) -> None:
        """Detach ``writer`` if it is still the attached one."""
        with self._lock:
            if self._stream_writer is writer:
                self._stream_writer = None


def _log_eviction(victim: HttpSession, cap: int) -> None:
    """Report an eviction, loudly only when the victim was in use.

    Every ``initialize`` mints a session, including for the many clients that
    ignore the header and never come back. Evicting one of those is routine
    capacity work; evicting a session a client is actually holding means the
    cap is too low for the load, and that is worth a warning.
    """
    abandoned = not victim.has_stream and victim.last_seen == victim.created_at
    if abandoned:
        autocontrol_logger.info(
            "MCP session cap %d reached — evicting a session that was never "
            "used after initialize", cap,
        )
        return
    autocontrol_logger.warning(
        "MCP session cap %d reached — evicting a live session (%s); raise "
        "the cap if clients are being dropped mid-conversation",
        cap, victim.id,
    )


class SessionRegistry:
    """Bounded, sweeping registry of :class:`HttpSession` by id.

    ``on_drop`` is invoked — outside the registry lock — for every session
    the registry removes, whichever way it goes: explicit termination, idle
    sweep, capacity eviction or shutdown. The transport uses it to release
    the dispatcher state scoped to that session id.
    """

    def __init__(self, *,
                 max_sessions: int = DEFAULT_MAX_SESSIONS,
                 idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
                 clock: Callable[[], float] = time.monotonic,
                 on_drop: Optional[Callable[[HttpSession], None]] = None,
                 ) -> None:
        self._sessions: Dict[str, HttpSession] = {}
        self._lock = threading.Lock()
        self._max_sessions = max(1, int(max_sessions))
        self._idle_timeout = float(idle_timeout)
        self._clock = clock
        self._on_drop = on_drop

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def create(self) -> HttpSession:
        """Mint a session, sweeping expired ones and honouring the cap."""
        session_id = secrets.token_urlsafe(_ID_ENTROPY_BYTES)
        now = self._clock()
        dropped: List[HttpSession] = []
        with self._lock:
            dropped.extend(self._expired_locked(now))
            while len(self._sessions) >= self._max_sessions:
                victim = min(self._sessions.values(),
                             key=lambda item: item.last_seen)
                del self._sessions[victim.id]
                dropped.append(victim)
                _log_eviction(victim, self._max_sessions)
            session = HttpSession(session_id, now)
            self._sessions[session_id] = session
        self._announce(dropped)
        return session

    def get(self, session_id: Optional[str]) -> Optional[HttpSession]:
        """Return the live session for ``session_id``, touching it."""
        if not session_id:
            return None
        now = self._clock()
        dropped: List[HttpSession] = []
        with self._lock:
            dropped.extend(self._expired_locked(now))
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_seen = now
        self._announce(dropped)
        return session

    def terminate(self, session_id: Optional[str]) -> Optional[HttpSession]:
        """Drop ``session_id`` and close its stream; None when unknown."""
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            self._announce([session])
        return session

    def terminate_all(self) -> List[HttpSession]:
        """Drop every session — used when the transport shuts down."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        self._announce(sessions)
        return sessions

    def _expired_locked(self, now: float) -> List[HttpSession]:
        """Remove idle sessions; caller holds the lock and announces."""
        if self._idle_timeout <= 0:
            return []
        stale = [session for session in self._sessions.values()
                 if now - session.last_seen > self._idle_timeout]
        for session in stale:
            del self._sessions[session.id]
        return stale

    def _announce(self, dropped: List[HttpSession]) -> None:
        """Close each dropped session's stream, then report it."""
        for session in dropped:
            session.closed.set()
            if self._on_drop is None:
                continue
            try:
                self._on_drop(session)
            except (RuntimeError, OSError, ValueError, KeyError,
                    AttributeError) as error:
                # A session can be dropped from a sweep triggered by an
                # unrelated request; a failing hook must not surface there.
                autocontrol_logger.warning(
                    "MCP session drop hook failed for %s: %r",
                    session.id, error,
                )


def session_id_from_headers(headers: Any) -> Optional[str]:
    """Read ``Mcp-Session-Id`` off a request's headers, or ``None``."""
    if headers is None:
        return None
    raw = headers.get(SESSION_HEADER)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


__all__ = [
    "DEFAULT_IDLE_TIMEOUT", "DEFAULT_MAX_SESSIONS", "HttpSession",
    "SESSION_HEADER", "SessionRegistry", "session_id_from_headers",
]
