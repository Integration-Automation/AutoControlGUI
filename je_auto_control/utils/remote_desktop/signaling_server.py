"""Standalone rendezvous service for WebRTC SDP exchange.

Hosts register an offer keyed by their host ID; viewers fetch the offer,
post an answer, and the host polls for it. The server is stateless beyond
an in-memory dict with TTL eviction — restart loses pending sessions.

It also serves ``GET`` / ``PUT /config/{user_id}``, the per-user bucket that
:mod:`je_auto_control.utils.config_sync` pushes and pulls. Buckets are kept
in memory as sent (no TTL), so they too are lost on restart.

Run::

    python -m je_auto_control.utils.remote_desktop.signaling_server \\
        --bind 127.0.0.1 --port 8765

Optional ``--shared-secret`` requires every request to carry a matching
``X-Signaling-Secret`` header (cheap protection against drive-by use).

Deployment: drop behind nginx + TLS on a small VPS. The server itself
is single-process; for HA put two instances behind a sticky load balancer
or swap the in-memory store for Redis (left as a follow-up).
"""
from __future__ import annotations

import argparse
import hmac
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Annotated, Dict, List, Optional

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - optional dep
    raise ImportError(
        "Signaling server requires the 'signaling' extra: "
        "pip install je_auto_control[signaling]"
    ) from exc


_DEFAULT_TTL_S = 120.0
_MAX_SDP_BYTES = 256 * 1024  # 256 KB; aiortc offers are typically ~4 KB
# Live sessions at once. Any client allowed to post could otherwise create
# sessions without limit -- 200 of them held 48 MB for the TTL.
_MAX_SESSIONS = 1024
# A config-sync bucket (hotkeys, triggers, address book) and how many users
# may hold one at once.
_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_CONFIG_USERS = 1024
_LOG = logging.getLogger("rd-signaling")
_WEB_VIEWER_DIR = (
    __import__("pathlib").Path(__file__).parent / "web_viewer"
)


@dataclass
class _Session:
    offer_sdp: Optional[str] = None
    answer_sdp: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)


class _ConfigStore:
    """Thread-safe in-memory map of user id -> config-sync bucket."""

    def __init__(self) -> None:
        self._buckets: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def get(self, user_id: str) -> Optional[Dict]:
        with self._lock:
            return self._buckets.get(user_id)

    def put(self, user_id: str, bucket: Dict) -> bool:
        """Store ``bucket``; ``False`` when a new user would exceed the cap."""
        with self._lock:
            if user_id not in self._buckets and len(self._buckets) >= _MAX_CONFIG_USERS:
                return False
            self._buckets[user_id] = bucket
            return True


class _SessionStore:
    """Thread-safe in-memory session map with TTL eviction."""

    def __init__(self, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._ttl_s = ttl_s
        self._lock = threading.Lock()

    def upsert_offer(self, host_id: str, offer_sdp: str) -> bool:
        """Store the offer; ``False`` when a new session would exceed the cap."""
        with self._lock:
            self._evict_locked()
            if host_id not in self._sessions and len(self._sessions) >= _MAX_SESSIONS:
                return False
            session = self._sessions.get(host_id) or _Session()
            session.offer_sdp = offer_sdp
            session.answer_sdp = None
            session.updated_at = time.monotonic()
            self._sessions[host_id] = session
            return True

    def fetch_offer(self, host_id: str) -> Optional[str]:
        with self._lock:
            self._evict_locked()
            session = self._sessions.get(host_id)
            return session.offer_sdp if session else None

    def upsert_answer(self, host_id: str, answer_sdp: str) -> bool:
        with self._lock:
            self._evict_locked()
            session = self._sessions.get(host_id)
            if session is None or session.offer_sdp is None:
                return False
            session.answer_sdp = answer_sdp
            session.updated_at = time.monotonic()
            return True

    def fetch_answer(self, host_id: str) -> Optional[str]:
        with self._lock:
            self._evict_locked()
            session = self._sessions.get(host_id)
            return session.answer_sdp if session else None

    def delete(self, host_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(host_id, None) is not None

    def _evict_locked(self) -> None:
        cutoff = time.monotonic() - self._ttl_s
        stale = [hid for hid, s in self._sessions.items()
                 if s.updated_at < cutoff]
        for host_id in stale:
            self._sessions.pop(host_id, None)


class _OfferIn(BaseModel):
    sdp: str


class _AnswerIn(BaseModel):
    sdp: str


_AUTH_RESPONSES = {401: {"description": "bad shared secret"}}
_VALIDATION_RESPONSES = {
    400: {"description": "invalid host_id or sdp"},
    **_AUTH_RESPONSES,
}
_OFFER_RESPONSES = {
    **_VALIDATION_RESPONSES,
    503: {"description": "too many live sessions"},
}
_NOT_FOUND_RESPONSES = {
    404: {"description": "session or message not found"},
    **_AUTH_RESPONSES,
}


def _build_secret_dependency(shared_secret: Optional[str]):
    """Return a FastAPI dependency that enforces ``X-Signaling-Secret``."""
    def _check(
        x_signaling_secret: Annotated[
            Optional[str], Header(alias="X-Signaling-Secret"),
        ] = None,
    ) -> None:
        if not _secret_matches(x_signaling_secret, shared_secret):
            raise HTTPException(status_code=401, detail="bad shared secret")
    return _check


def _validate_host_id(host_id: str) -> None:
    if not host_id or len(host_id) > 128 or not host_id.isalnum():
        # 400 is documented at every caller route via _VALIDATION_RESPONSES.
        raise HTTPException(status_code=400, detail="invalid host_id")  # NOSONAR — see _VALIDATION_RESPONSES


def _validate_sdp(sdp: str) -> None:
    if not sdp or len(sdp.encode("utf-8")) > _MAX_SDP_BYTES:
        # 400 is documented at every caller route via _VALIDATION_RESPONSES.
        raise HTTPException(status_code=400, detail="invalid sdp size")  # NOSONAR — see _VALIDATION_RESPONSES


def _configure_cors(app: FastAPI, cors_origins: Optional[List[str]]) -> None:
    # ``["*"]`` is the documented default — the signaling server is
    # meant to be reached from any browser tab running the viewer SPA;
    # access control runs at the X-Signaling-Secret layer, not Origin.
    # Operators tighten this via the repeatable --cors-origin CLI flag.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],  # nosemgrep: python.fastapi.security.wildcard-cors.wildcard-cors
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Signaling-Secret"],
    )


def _maybe_mount_viewer(app: FastAPI, serve_web_viewer: bool) -> None:
    if serve_web_viewer and _WEB_VIEWER_DIR.exists():
        app.mount(
            "/viewer",
            StaticFiles(directory=str(_WEB_VIEWER_DIR), html=True),
            name="viewer",
        )


def _register_routes(app: FastAPI, store: "_SessionStore",
                     secret_dep) -> None:
    # Apply the auth dependency at the route layer so each handler's
    # signature stays free of plumbing parameters. The dependency
    # itself uses the recommended ``Annotated[Optional[str], Header(...)]``
    # form for its ``X-Signaling-Secret`` parameter — see
    # ``_build_secret_dependency`` above.
    auth_only = [Depends(secret_dep)]

    @app.get("/health")
    def _health() -> dict:
        return {"status": "ok"}

    @app.post("/sessions/{host_id}/offer",
              responses=_OFFER_RESPONSES, dependencies=auth_only)
    def _post_offer(host_id: str, body: _OfferIn) -> dict:
        _validate_host_id(host_id)
        _validate_sdp(body.sdp)
        if not store.upsert_offer(host_id, body.sdp):
            raise HTTPException(status_code=503, detail="too many live sessions")  # NOSONAR - see _OFFER_RESPONSES
        return {"ok": True}

    @app.get("/sessions/{host_id}/offer",
             responses=_NOT_FOUND_RESPONSES, dependencies=auth_only)
    def _get_offer(host_id: str) -> dict:
        _validate_host_id(host_id)
        sdp = store.fetch_offer(host_id)
        if sdp is None:
            raise HTTPException(status_code=404, detail="no offer pending")
        return {"sdp": sdp}

    @app.post("/sessions/{host_id}/answer",
              responses={**_VALIDATION_RESPONSES, **_NOT_FOUND_RESPONSES},
              dependencies=auth_only)
    def _post_answer(host_id: str, body: _AnswerIn) -> dict:
        _validate_host_id(host_id)
        _validate_sdp(body.sdp)
        if not store.upsert_answer(host_id, body.sdp):
            # 404 documented via _NOT_FOUND_RESPONSES on this route.
            raise HTTPException(status_code=404, detail="no offer to match")  # NOSONAR
        return {"ok": True}

    @app.get("/sessions/{host_id}/answer",
             responses=_NOT_FOUND_RESPONSES, dependencies=auth_only)
    def _get_answer(host_id: str) -> dict:
        _validate_host_id(host_id)
        sdp = store.fetch_answer(host_id)
        if sdp is None:
            raise HTTPException(status_code=404, detail="no answer yet")
        return {"sdp": sdp}

    @app.delete("/sessions/{host_id}",
                responses=_AUTH_RESPONSES, dependencies=auth_only)
    def _delete(host_id: str) -> dict:
        _validate_host_id(host_id)
        return {"deleted": store.delete(host_id)}


#: Room for the JSON wrapper around the largest SDP a route accepts.
_MAX_BODY_BYTES = _MAX_SDP_BYTES + 4096


def _secret_matches(provided: Optional[str], shared_secret: Optional[str]) -> bool:
    # compare_digest on bytes: != leaks how much of the secret matched.
    return not shared_secret or hmac.compare_digest(
        (provided or "").encode("utf-8"), shared_secret.encode("utf-8"))


def _guard_refusal(request: Request, shared_secret: Optional[str]) -> Optional[JSONResponse]:
    """The response refusing ``request`` before its body is read, or ``None``.

    FastAPI reads and parses the body before it resolves route dependencies,
    so a client without the secret made the server buffer a body of any size
    (30 MB cost ~95 MB) and got JSON validation details back instead of 401.
    """
    path = request.url.path
    if not path.startswith(("/sessions", "/config")) or request.method == "OPTIONS":
        return None
    if not _secret_matches(request.headers.get("X-Signaling-Secret"), shared_secret):
        return JSONResponse({"detail": "bad shared secret"}, status_code=401)
    if request.method not in ("POST", "PUT"):
        return None
    length = request.headers.get("Content-Length")
    if length is None or not length.isdigit():
        return JSONResponse({"detail": "Content-Length required"}, status_code=411)
    limit = _MAX_CONFIG_BYTES if path.startswith("/config") else _MAX_BODY_BYTES
    if int(length) > limit:
        return JSONResponse({"detail": "request body too large"}, status_code=413)
    return None


def _register_body_guard(app: FastAPI, shared_secret: Optional[str]) -> None:
    @app.middleware("http")
    async def _guard(request: Request, call_next):
        refusal = _guard_refusal(request, shared_secret)
        return refusal if refusal is not None else await call_next(request)


def _validate_user_id(user_id: str) -> None:
    # Printable, no path separators: the id is a single URL path segment.
    if not user_id or len(user_id) > 128 or not user_id.isprintable() or "/" in user_id:
        raise HTTPException(status_code=400, detail="invalid user_id")  # NOSONAR — see _CONFIG_RESPONSES


_CONFIG_RESPONSES = {
    400: {"description": "invalid user_id or bucket"},
    404: {"description": "no bucket for this user"},
    503: {"description": "too many users"},
    **_AUTH_RESPONSES,
}


def _register_config_routes(app: FastAPI, store: _ConfigStore, secret_dep) -> None:
    """``GET`` / ``PUT /config/{user_id}`` for :mod:`je_auto_control.utils.config_sync`.

    The client has always called these; nothing served them, so every sync
    failed. A bucket is stored as sent -- the merge happens client-side.
    """
    auth_only = [Depends(secret_dep)]

    @app.get("/config/{user_id}", responses=_CONFIG_RESPONSES, dependencies=auth_only)
    def _get_config(user_id: str) -> dict:
        _validate_user_id(user_id)
        bucket = store.get(user_id)
        if bucket is None:
            raise HTTPException(status_code=404, detail="no bucket")  # NOSONAR — see _CONFIG_RESPONSES
        return bucket

    @app.put("/config/{user_id}", responses=_CONFIG_RESPONSES, dependencies=auth_only)
    def _put_config(user_id: str, bucket: Dict) -> dict:
        _validate_user_id(user_id)
        if bucket.get("user_id", user_id) != user_id:
            raise HTTPException(status_code=400, detail="bucket user_id mismatch")  # NOSONAR — see _CONFIG_RESPONSES
        if not store.put(user_id, bucket):
            raise HTTPException(status_code=503, detail="too many users")  # NOSONAR — see _CONFIG_RESPONSES
        return {"ok": True}


def _register_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def _log_request(request: Request, call_next):
        response = await call_next(request)
        _LOG.info("%s %s -> %d", request.method, request.url.path,
                  response.status_code)
        return response


def create_app(shared_secret: Optional[str] = None,
               ttl_s: float = _DEFAULT_TTL_S,
               serve_web_viewer: bool = True,
               cors_origins: Optional[list] = None) -> FastAPI:
    """Build the FastAPI app. Importable for embedding in larger services."""
    app = FastAPI(title="AutoControl Signaling", version="1.0.0")
    store = _SessionStore(ttl_s=ttl_s)
    # Before CORS, so CORS wraps it and a browser still sees the 401 / 413.
    _register_body_guard(app, shared_secret)
    _configure_cors(app, cors_origins)
    _maybe_mount_viewer(app, serve_web_viewer)
    secret_dep = _build_secret_dependency(shared_secret)
    _register_routes(app, store, secret_dep)
    _register_config_routes(app, _ConfigStore(), secret_dep)
    _register_request_logging(app)
    return app


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="je_auto_control.utils.remote_desktop.signaling_server",
        description="WebRTC signaling rendezvous service for AutoControl.",
    )
    parser.add_argument("--bind", default="127.0.0.1",
                        help="bind address (default: 127.0.0.1)")
    parser.add_argument("--port", default=8765, type=int,
                        help="listen port (default: 8765)")
    parser.add_argument("--shared-secret", default=None,
                        help="if set, every request must send "
                             "X-Signaling-Secret matching this value")
    parser.add_argument("--ttl-seconds", default=_DEFAULT_TTL_S, type=float,
                        help="session eviction TTL in seconds")
    parser.add_argument("--no-web-viewer", action="store_true",
                        help="don't mount the bundled web viewer at /viewer")
    parser.add_argument("--cors-origin", action="append", default=None,
                        help="allowed CORS origin (repeatable; default: *)")
    return parser


def main(argv: Optional[list] = None) -> None:
    """Entry point: parse args and start uvicorn."""
    try:
        import uvicorn  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "uvicorn missing; install with pip install "
            "je_auto_control[signaling]",
        ) from exc
    args = _build_arg_parser().parse_args(argv)
    secret = args.shared_secret or os.environ.get("AC_SIGNALING_SECRET")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(
        shared_secret=secret,
        ttl_s=args.ttl_seconds,
        serve_web_viewer=not args.no_web_viewer,
        cors_origins=args.cors_origin,
    )
    uvicorn.run(app, host=args.bind, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
