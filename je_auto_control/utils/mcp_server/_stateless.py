"""MCP 2026-07-28, the stateless revision, served beside the handshake-based ones.

2026-07-28 removes ``initialize``: every request names its protocol version
and the client's capabilities in ``params._meta``, every result says whether
it is complete (``resultType``), and ``server/discover`` replaces the
handshake as the way to learn the server's versions and capabilities. A
server that speaks both eras ("dual-era", MCP versioning) decides per
request: one whose ``_meta`` names a protocol version is served statelessly,
while ``initialize`` and every request without that key are served the way
the older revisions define.

Nothing in a stateless request is read from the connection. The capabilities
the gates consult are the request's own; the server sends no request of its
own (the destructive-tool confirmation becomes a multi round-trip result, see
:mod:`._input_required`); and no notification goes out that the client did not
ask for: log records only for a request that set
``io.modelcontextprotocol/logLevel``, and none of the unsolicited list-change
or resource notifications the handshake era sends.
"""
import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Tuple

from je_auto_control.utils.mcp_server._client_requests import needs_confirmation
from je_auto_control.utils.mcp_server._input_required import (
    RequestStateSigner, require_confirmation,
)
from je_auto_control.utils.mcp_server._protocol import (
    SUPPORTED_PROTOCOL_VERSIONS, _MCPError, _server_info,
)
from je_auto_control.utils.mcp_server.log_bridge import mcp_level_to_logging
from je_auto_control.utils.mcp_server.tools import MCPTool

STATELESS_PROTOCOL_VERSION = "2026-07-28"
#: Revisions served per request, newest first.
STATELESS_PROTOCOL_VERSIONS = (STATELESS_PROTOCOL_VERSION,)

META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

#: Error codes the specification reserves (-32020 to -32099).
HEADER_MISMATCH = -32020
MISSING_REQUIRED_CLIENT_CAPABILITY = -32021
UNSUPPORTED_PROTOCOL_VERSION = -32022

DISCOVER_METHOD = "server/discover"
#: Methods a stateless request may call besides ``server/discover``. The
#: handshake era's ``initialize``, ``ping``, ``logging/setLevel`` and
#: ``resources/(un)subscribe`` are gone from 2026-07-28.
_STATELESS_METHODS = frozenset({
    "tools/list", "tools/call", "resources/list", "resources/read",
    "prompts/list", "prompts/get",
})
#: ``ttlMs`` of the cacheable results. Lists change only when a plugin is
#: loaded; a resource is read live (a screenshot, the run history), so it is
#: stale at once.
_CACHE_TTL_MS = {
    DISCOVER_METHOD: 3_600_000,
    "tools/list": 60_000, "prompts/list": 60_000, "resources/list": 60_000,
    "resources/read": 0,
}
#: The server's capabilities as a stateless client sees them.
STATELESS_CAPABILITIES: Dict[str, Any] = {"tools": {}, "resources": {}, "prompts": {}}


def all_supported_versions() -> Tuple[str, ...]:
    """Every revision this server speaks, stateless and handshake-era, newest first."""
    return STATELESS_PROTOCOL_VERSIONS + tuple(SUPPORTED_PROTOCOL_VERSIONS)


@dataclass(frozen=True)
class StatelessRequest:
    """What a 2026-07-28 request says about itself in ``_meta`` and its retry fields."""

    version: str
    capabilities: Dict[str, Any]
    log_level: Optional[int] = None
    input_responses: Optional[Dict[str, Any]] = None
    request_state: Optional[str] = None


def _invalid(message: str) -> _MCPError:
    return _MCPError(-32602, f"Invalid params: {message}")


def stateless_request(params: Dict[str, Any]) -> Optional[StatelessRequest]:
    """Read a request's 2026-07-28 metadata; ``None`` for a handshake-era request.

    Raises :class:`_MCPError`: ``-32022`` for a version this server does not
    serve statelessly (its ``data`` lists the supported ones) and ``-32602``
    for missing or malformed per-request fields.
    """
    meta = params.get("_meta")
    if not isinstance(meta, dict) or META_PROTOCOL_VERSION not in meta:
        return None
    version = meta[META_PROTOCOL_VERSION]
    if version not in STATELESS_PROTOCOL_VERSIONS:
        raise _MCPError(UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
                        data={"supported": list(all_supported_versions()), "requested": version})
    capabilities = meta.get(META_CLIENT_CAPABILITIES)
    if not isinstance(capabilities, dict):
        raise _invalid(f"_meta must carry {META_CLIENT_CAPABILITIES} as an object")
    input_responses = _optional(params, "inputResponses", dict, "an object")
    request_state = _optional(params, "requestState", str, "a string")
    return StatelessRequest(version=version, capabilities=dict(capabilities),
                            log_level=_log_level(meta), input_responses=input_responses,
                            request_state=request_state)


def _log_level(meta: Dict[str, Any]) -> Optional[int]:
    """The request's ``logLevel`` as a :mod:`logging` level, ``None`` when unset."""
    if META_LOG_LEVEL not in meta:
        return None
    level = mcp_level_to_logging(meta[META_LOG_LEVEL])
    if level is None:
        raise _invalid(f"unknown log level {meta[META_LOG_LEVEL]!r}")
    return level


def _optional(params: Dict[str, Any], key: str, kind: type, described: str) -> Any:
    """``params[key]`` when it is absent or a ``kind``; invalid params otherwise."""
    value = params.get(key)
    if value is not None and not isinstance(value, kind):
        raise _invalid(f"{key} must be {described}")
    return value


def discover_result() -> Dict[str, Any]:
    """The body of a ``server/discover`` result."""
    return {"supportedVersions": list(all_supported_versions()),
            "capabilities": STATELESS_CAPABILITIES}


def shape_result(method: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Give a handler's result the fields every 2026-07-28 result carries.

    ``resultType`` (``complete`` unless the handler asked for input), the
    server's identity in ``_meta``, and ``ttlMs`` / ``cacheScope`` on the
    cacheable complete results. ``private``: resources hold what is on this
    user's screen, and the lists follow this server's read-only setting.
    """
    shaped = dict(result)
    shaped.setdefault("resultType", "complete")
    meta = dict(shaped.get("_meta") or {})
    meta[META_SERVER_INFO] = _server_info(STATELESS_PROTOCOL_VERSION)
    shaped["_meta"] = meta
    if shaped["resultType"] == "complete" and method in _CACHE_TTL_MS:
        shaped["ttlMs"] = _CACHE_TTL_MS[method]
        shaped["cacheScope"] = "private"
    return shaped


class StatelessDispatchMixin:
    """Per-request routing between the two eras, mixed into :class:`MCPServer`.

    Requires the host to provide ``_local`` (thread-local storage),
    ``_log_bridge``, ``_peer_era``, ``_request_states``, ``_connection_id``,
    ``_notifier`` and ``_run_method`` (the handshake-era method table).
    """

    if TYPE_CHECKING:
        _local: Any
        _log_bridge: Any
        _peer_era: Optional[str]
        _request_states: RequestStateSigner

        @property
        def _connection_id(self) -> Any:
            """Identity of the connection the current request arrived on."""

        @property
        def _notifier(self) -> Any:
            """The notifier bound to the current thread or connection."""

        def _run_method(self, msg_id: Any, method: Optional[str],
                        params: Dict[str, Any]) -> Any:
            """Run a method from the handshake-era table."""

    @property
    def _stateless_request(self) -> Optional[StatelessRequest]:
        """The 2026-07-28 request being served on this thread, if any."""
        return getattr(self._local, "stateless", None)

    def _dispatch(self, msg_id: Any, method: Optional[str],
                  params: Dict[str, Any]) -> Any:
        """Serve ``method`` in the era the request declares."""
        request = None if method == "initialize" else stateless_request(params)
        if request is None:
            if method == DISCOVER_METHOD:
                raise _invalid(f"{DISCOVER_METHOD} needs _meta {META_PROTOCOL_VERSION} "
                               f"and {META_CLIENT_CAPABILITIES}")
            return self._run_method(msg_id, method, params)
        if method != DISCOVER_METHOD and method not in _STATELESS_METHODS:
            raise _MCPError(-32601, f"Method not found: {method}")
        self._note_peer_era("stateless")
        with self._stateless_scope(request):
            result = (discover_result() if method == DISCOVER_METHOD
                      else self._run_method(msg_id, method, params))
        return shape_result(method, result)

    @contextlib.contextmanager
    def _stateless_scope(self, request: StatelessRequest) -> Iterator[None]:
        """Serve the calling thread's request from its own metadata only."""
        prior = self._stateless_request
        self._local.stateless = request
        bridge = self._log_bridge
        logs = (bridge.request_scope(request.log_level) if bridge is not None
                else contextlib.nullcontext())
        try:
            with logs:
                yield
        finally:
            self._local.stateless = prior

    def _note_peer_era(self, era: str) -> None:
        """Record which era the stdio peer speaks; the handshake always wins.

        Unsolicited notifications (log records outside any request, list
        changes) go to a handshake-era peer only.
        """
        if self._connection_id is not None:
            return
        if era == "stateless" and self._peer_era is not None:
            return
        self._peer_era = era
        if self._log_bridge is not None:
            self._log_bridge.forward_unscoped = era != "stateless"

    def _unsolicited_notifier(self) -> Any:
        """The notifier for a notification no request asked for, or ``None``."""
        if self._stateless_request is not None:
            return None
        if self._connection_id is None and self._peer_era == "stateless":
            return None
        return self._notifier

    def _maybe_confirm_destructive(self, name: str, tool: MCPTool,
                                   arguments: Dict[str, Any]) -> None:
        """Confirm a destructive call by multi round-trip in a stateless request."""
        request = self._stateless_request
        if request is None:
            super()._maybe_confirm_destructive(name, tool, arguments)  # type: ignore[misc]
            return
        if not needs_confirmation(tool):
            return
        # The handshake era runs such a call unprompted for a client without
        # elicitation; 2026-07-28 names the capability the call needs instead.
        if "elicitation" not in request.capabilities:
            raise _MCPError(MISSING_REQUIRED_CLIENT_CAPABILITY,
                            f"Confirming {name} needs the elicitation capability",
                            data={"requiredCapabilities": {"elicitation": {}}})
        require_confirmation(self._request_states, name, arguments,
                             request.input_responses, request.request_state)
