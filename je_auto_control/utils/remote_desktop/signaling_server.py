"""Standalone rendezvous service for WebRTC SDP exchange.

Hosts register an offer keyed by their host ID; viewers fetch the offer,
post an answer, and the host polls for it. The server is stateless beyond
an in-memory dict with TTL eviction — restart loses pending sessions.

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
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Annotated, Dict, List, Optional

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - optional dep
    raise ImportError(
        "Signaling server requires the 'signaling' extra: "
        "pip install je_auto_control[signaling]"
    ) from exc


_DEFAULT_TTL_S = 120.0
_MAX_SDP_BYTES = 256 * 1024  # 256 KB; aiortc offers are typically ~4 KB
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


class _SessionStore:
    """Thread-safe in-memory session map with TTL eviction."""

    def __init__(self, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._ttl_s = ttl_s
        self._lock = threading.Lock()

    def upsert_offer(self, host_id: str, offer_sdp: str) -> None:
        with self._lock:
            self._evict_locked()
            session = self._sessions.get(host_id) or _Session()
            session.offer_sdp = offer_sdp
            session.answer_sdp = None
            session.updated_at = time.monotonic()
            self._sessions[host_id] = session

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
        if shared_secret and x_signaling_secret != shared_secret:
            raise HTTPException(status_code=401, detail="bad shared secret")
    return _check


def _validate_host_id(host_id: str) -> None:
    if not host_id or len(host_id) > 128 or not host_id.isalnum():
        raise HTTPException(status_code=400, detail="invalid host_id")


def _validate_sdp(sdp: str) -> None:
    if not sdp or len(sdp.encode("utf-8")) > _MAX_SDP_BYTES:
        raise HTTPException(status_code=400, detail="invalid sdp size")


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
              responses=_VALIDATION_RESPONSES, dependencies=auth_only)
    def _post_offer(host_id: str, body: _OfferIn) -> dict:
        _validate_host_id(host_id)
        _validate_sdp(body.sdp)
        store.upsert_offer(host_id, body.sdp)
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
            raise HTTPException(status_code=404, detail="no offer to match")
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
    _configure_cors(app, cors_origins)
    _maybe_mount_viewer(app, serve_web_viewer)
    _register_routes(app, store, _build_secret_dependency(shared_secret))
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
