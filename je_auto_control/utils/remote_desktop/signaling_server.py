"""Standalone rendezvous service for WebRTC SDP exchange.

Hosts register an offer keyed by their host ID; viewers fetch the offer,
post an answer, and the host polls for it. Sessions live in an in-memory
dict with TTL eviction — restart loses pending sessions.

It also serves ``GET`` / ``PUT /config/{user_id}``, the per-user bucket that
:mod:`je_auto_control.utils.config_sync` pushes and pulls. Buckets live in a
SQLite file (``--config-db``, ``AC_SIGNALING_CONFIG_DB``, default
``~/.je_auto_control/config_sync.sqlite3``; opened at the first ``/config``
request), so they survive a restart. A ``PUT`` is a version-2 envelope::

    {"version": 2, "base_revision": 3, "operation_id": "<unique id>",
     "bucket": {"user_id": "...", "sections": {...}}}

and is committed only while the stored bucket is still at ``base_revision``
(``0`` = no bucket yet): ``200 {"ok": true, "revision": 4}``, or ``409
{"detail": "revision conflict", "revision": <current>}`` when another write
got there first. Repeating a ``PUT`` with the same ``operation_id`` returns
the revision the first one produced; the same ``operation_id`` with a
different bucket or base revision is ``409 {"code": "operation_mismatch",
"revision": <the first write's>}`` and writes nothing. ``GET`` returns the bucket with
``revision`` set to the committed revision and ``"version": 2``. A bare
bucket (what clients sent before version 2) is answered ``428`` unless the
server runs with ``--allow-blind-config-writes``, which restores the
unconditional overwrite those clients expect.

It also keeps the *assets* config sync cannot fit in a bucket entry, as
content-addressed blobs per account::

    PUT    /blobs/{user_id}/{sha256}   raw bytes; 201 stored, 200 already held
    GET    /blobs/{user_id}/{sha256}   the bytes, or 404
    HEAD   /blobs/{user_id}/{sha256}   200 / 404, no body
    DELETE /blobs/{user_id}/{sha256}   {"deleted": true | false}
    GET    /blobs/{user_id}            {"used", "quota", "count", "max_blob_bytes",
                                        "blobs": [{"sha256", "size", "age_s"}]}

under the rules ``/config`` follows: the shared secret, the account named by
the path (one account never reads another's blob), and a size cap checked
against ``Content-Length`` before the body is read (``--max-blob-bytes``,
default 16 MiB; ``413`` over it, ``411`` without a length). The server hashes
what it receives and answers ``400`` unless it matches the digest in the
path. ``--blob-quota-bytes`` (default 256 MiB) bounds what one account may
hold in total: ``507`` once a blob would not fit. Blobs live in
``--blob-dir`` (default: the config database's path with ``.blobs`` added),
created at the first upload. These routes are additions; the ``/config``
wire format is still version 2.

Run::

    python -m je_auto_control.utils.remote_desktop.signaling_server \\
        --bind 127.0.0.1 --port 8765

Optional ``--shared-secret`` requires every request to carry a matching
``X-Signaling-Secret`` header (cheap protection against drive-by use).

Deployment: drop behind nginx + TLS on a small VPS. The server itself
is single-process; for HA put two instances behind a sticky load balancer
or swap the in-memory session store for Redis (left as a follow-up); the
config buckets are already safe to share, as every commit is one SQLite
transaction.
"""
from __future__ import annotations

import argparse
import hmac
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Tuple

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.concurrency import run_in_threadpool
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - optional dep
    raise ImportError(
        "Signaling server requires the 'signaling' extra: "
        "pip install je_auto_control[signaling]"
    ) from exc

from je_auto_control.utils.config_sync.blobs import (
    DEFAULT_BLOB_QUOTA_BYTES, DEFAULT_MAX_BLOB_BYTES, BlobCapacityError, BlobDigestError,
    BlobQuotaError, BlobStore, BlobStoreError, BlobTooLargeError,
)
from je_auto_control.utils.config_sync.bucket import (
    ConfigBucket, ConfigSyncError, OperationMismatchError,
)
from je_auto_control.utils.config_sync.store import (
    ConfigStore, RevisionConflictError, StoreCapacityError, default_store_path,
)


_DEFAULT_TTL_S = 120.0
_MAX_SDP_BYTES = 256 * 1024  # 256 KB; aiortc offers are typically ~4 KB
# Live sessions at once. Any client allowed to post could otherwise create
# sessions without limit -- 200 of them held 48 MB for the TTL.
_MAX_SESSIONS = 1024
# A config-sync PUT body (the bucket plus its envelope) and how many users
# may hold a bucket at once.
_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_CONFIG_USERS = 1024
#: The ``/config`` wire format this server speaks.
CONFIG_WIRE_VERSION = 2
#: ``code`` of the 409 that refuses an operation id reused for other content.
CONFIG_OPERATION_MISMATCH = "operation_mismatch"
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


def _guard_refusal(request: Request, shared_secret: Optional[str],
                   max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> Optional[JSONResponse]:
    """The response refusing ``request`` before its body is read, or ``None``.

    FastAPI reads and parses the body before it resolves route dependencies,
    so a client without the secret made the server buffer a body of any size
    (30 MB cost ~95 MB) and got JSON validation details back instead of 401.
    """
    # scope["path"] is what the router dispatches on. request.url is rebuilt
    # from the Host header, and Starlette <= 1.0.0 let a crafted Host
    # ("example.com?") make it show another path (CVE-2026-48710, "BadHost"),
    # which would slip a request past a guard deciding by request.url.path.
    path = str(request.scope.get("path", ""))
    if not path.startswith(("/sessions", "/config", "/blobs")) or request.method == "OPTIONS":
        return None
    if not _secret_matches(request.headers.get("X-Signaling-Secret"), shared_secret):
        return JSONResponse({"detail": "bad shared secret"}, status_code=401)
    if request.method not in ("POST", "PUT"):
        return None
    length = request.headers.get("Content-Length")
    if length is None or not length.isdigit():
        return JSONResponse({"detail": "Content-Length required"}, status_code=411)
    if int(length) > _body_limit(path, max_blob_bytes):
        return JSONResponse({"detail": "request body too large"}, status_code=413)
    return None


def _body_limit(path: str, max_blob_bytes: int) -> int:
    """The largest body a POST / PUT to ``path`` may announce."""
    if path.startswith("/blobs"):
        return max_blob_bytes
    return _MAX_CONFIG_BYTES if path.startswith("/config") else _MAX_BODY_BYTES


def _register_body_guard(app: FastAPI, shared_secret: Optional[str],
                         max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> None:
    @app.middleware("http")
    async def _guard(request: Request, call_next):
        refusal = _guard_refusal(request, shared_secret, max_blob_bytes)
        return refusal if refusal is not None else await call_next(request)


def _validate_user_id(user_id: str) -> None:
    # Printable, no path separators: the id is a single URL path segment.
    if not user_id or len(user_id) > 128 or not user_id.isprintable() or "/" in user_id:
        raise HTTPException(status_code=400, detail="invalid user_id")  # NOSONAR — see _CONFIG_RESPONSES


_CONFIG_RESPONSES = {
    400: {"description": "invalid user_id, envelope or bucket"},
    404: {"description": "no bucket for this user"},
    409: {"description": "base_revision is not the current revision, or (code "
                         "operation_mismatch) operation_id was used for another write"},
    428: {"description": "a write without base_revision / operation_id"},
    503: {"description": "too many users, or the store is unavailable"},
    **_AUTH_RESPONSES,
}


def _config_bucket(user_id: str, body: Any) -> ConfigBucket:
    """Validate ``body`` as the bucket of ``user_id`` (400 otherwise)."""
    try:
        bucket = ConfigBucket.from_dict(body)
    except ConfigSyncError as error:
        raise HTTPException(status_code=400, detail=f"invalid bucket: {error}") from error  # NOSONAR
    # Account isolation: the path names the account, the body cannot move it.
    if bucket.user_id != user_id:
        raise HTTPException(status_code=400, detail="bucket user_id mismatch")  # NOSONAR
    return bucket


def _config_envelope(body: Dict[str, Any]) -> Optional[Tuple[Any, int, str]]:
    """``(bucket, base_revision, operation_id)`` of a version-2 PUT body.

    ``None`` for a bare bucket -- the pre-version-2 body, recognised by
    having neither ``version`` nor ``bucket``.
    """
    if "version" not in body and "bucket" not in body:
        return None
    base = body.get("base_revision")
    operation = body.get("operation_id")
    if (body.get("version") == CONFIG_WIRE_VERSION
            and isinstance(base, int) and not isinstance(base, bool) and base >= 0
            and isinstance(operation, str) and 0 < len(operation) <= 128
            and operation.isprintable()):
        return body.get("bucket"), base, operation
    raise HTTPException(  # NOSONAR — see _CONFIG_RESPONSES
        status_code=400,
        detail="expected {version: 2, base_revision: int >= 0, operation_id: str, bucket: {...}}")


def _commit_config(store: ConfigStore, user_id: str, body: Dict[str, Any],
                   allow_blind_writes: bool) -> int | JSONResponse:
    """Commit a PUT body; the new revision, or the 409 reply on a conflict."""
    envelope = _config_envelope(body)
    if envelope is None:
        if not allow_blind_writes:
            raise HTTPException(  # NOSONAR — see _CONFIG_RESPONSES
                status_code=428,
                detail="this server requires a version-2 write (base_revision and operation_id); "
                       "unconditional writes need --allow-blind-config-writes")
        return store.overwrite(user_id, _config_bucket(user_id, body))
    payload, base, operation = envelope
    bucket = _config_bucket(user_id, payload)
    try:
        return store.commit(user_id, bucket, base_revision=base, operation_id=operation)
    except RevisionConflictError as conflict:
        return JSONResponse({"detail": "revision conflict", "revision": conflict.current_revision},
                            status_code=409)
    except OperationMismatchError as mismatch:
        # 409 like a revision conflict, so a client that knows only that
        # status still learns nothing was written; ``code`` tells them apart.
        return JSONResponse(
            {"detail": "operation_id was already used for a different write",
             "code": CONFIG_OPERATION_MISMATCH, "revision": mismatch.revision},
            status_code=409)


def _register_config_routes(app: FastAPI, store: ConfigStore, secret_dep,
                            allow_blind_writes: bool = False) -> None:
    """``GET`` / ``PUT /config/{user_id}`` for :mod:`je_auto_control.utils.config_sync`.

    The merge happens client-side; the server's part is to keep the bucket
    and to refuse a write that was not built on the current revision.
    """
    auth_only = [Depends(secret_dep)]

    @app.get("/config/{user_id}", responses=_CONFIG_RESPONSES, dependencies=auth_only)
    def _get_config(user_id: str) -> dict:
        _validate_user_id(user_id)
        try:
            bucket = store.get(user_id)
        except ConfigSyncError as error:
            _LOG.error("config store read failed: %s", error)
            raise HTTPException(status_code=503, detail="config store unavailable") from error  # NOSONAR
        if bucket is None:
            raise HTTPException(status_code=404, detail="no bucket")  # NOSONAR — see _CONFIG_RESPONSES
        return {**bucket.to_dict(), "version": CONFIG_WIRE_VERSION}

    @app.put("/config/{user_id}", responses=_CONFIG_RESPONSES, dependencies=auth_only)
    def _put_config(user_id: str, body: Dict[str, Any]):
        _validate_user_id(user_id)
        try:
            outcome = _commit_config(store, user_id, body, allow_blind_writes)
        except StoreCapacityError as error:
            raise HTTPException(status_code=503, detail="too many users") from error  # NOSONAR
        except ConfigSyncError as error:
            _LOG.error("config store write failed: %s", error)
            raise HTTPException(status_code=503, detail="config store unavailable") from error  # NOSONAR
        if isinstance(outcome, JSONResponse):
            return outcome
        return {"ok": True, "revision": outcome, "version": CONFIG_WIRE_VERSION}


_BLOB_RESPONSES = {
    400: {"description": "invalid user_id or digest, or content that does not hash to it"},
    404: {"description": "the account holds no such blob"},
    413: {"description": "larger than one blob may be"},
    503: {"description": "too many accounts, or the store is unavailable"},
    507: {"description": "the account's quota is used up"},
    **_AUTH_RESPONSES,
}
_BLOB_FAILURES = (
    (BlobDigestError, 400), (BlobTooLargeError, 413), (BlobQuotaError, 507),
    (BlobCapacityError, 503),
)


def _blob_failure(error: BlobStoreError) -> HTTPException:
    """The HTTP error a blob-store failure stands for."""
    for kind, status in _BLOB_FAILURES:
        if isinstance(error, kind):
            return HTTPException(status_code=status, detail=str(error))
    _LOG.error("blob store failed: %s", error)
    return HTTPException(status_code=503, detail="blob store unavailable")


def _blob_call(action, *arguments):
    """Run one blob-store call, turning its failures into HTTP errors."""
    try:
        return action(*arguments)
    except BlobStoreError as error:
        raise _blob_failure(error) from error  # NOSONAR — see _BLOB_RESPONSES


def _register_blob_routes(app: FastAPI, blobs: BlobStore, secret_dep) -> None:
    """``/blobs/{user_id}/{sha256}`` for config sync's assets.

    Content-addressed and per account: the path names the account, the
    digest names the content, and the server checks the second itself.
    """
    auth_only = [Depends(secret_dep)]
    one = "/blobs/{user_id}/{digest}"

    @app.put(one, responses=_BLOB_RESPONSES, dependencies=auth_only)
    async def _put_blob(user_id: str, digest: str, request: Request):
        _validate_user_id(user_id)
        # Bounded: the guard refused anything announcing more than the cap.
        data = await request.body()
        stored = await run_in_threadpool(_blob_call, blobs.put, user_id, digest, data)
        return JSONResponse({"ok": True, "sha256": digest.lower(), "size": len(data),
                             "stored": stored}, status_code=201 if stored else 200)

    @app.get(one, responses=_BLOB_RESPONSES, dependencies=auth_only)
    def _get_blob(user_id: str, digest: str):
        _validate_user_id(user_id)
        data = _blob_call(blobs.get, user_id, digest)
        if data is None:
            raise HTTPException(status_code=404, detail="no such blob")  # NOSONAR
        return Response(content=data, media_type="application/octet-stream")

    @app.head(one, responses=_BLOB_RESPONSES, dependencies=auth_only)
    def _head_blob(user_id: str, digest: str):
        _validate_user_id(user_id)
        return Response(status_code=200 if _blob_call(blobs.has, user_id, digest) else 404)

    @app.delete(one, responses=_BLOB_RESPONSES, dependencies=auth_only)
    def _delete_blob(user_id: str, digest: str) -> dict:
        _validate_user_id(user_id)
        return {"deleted": _blob_call(blobs.delete, user_id, digest)}

    @app.get("/blobs/{user_id}", responses=_BLOB_RESPONSES, dependencies=auth_only)
    def _list_blobs(user_id: str) -> dict:
        _validate_user_id(user_id)
        return _blob_call(blobs.usage, user_id)


def _blob_root(blob_store_path: str | Path | None,
               config_store_path: str | Path | None) -> Path:
    """Where blobs go: the given folder, else beside the config database."""
    if blob_store_path is not None:
        return Path(blob_store_path)
    database = Path(config_store_path) if config_store_path is not None else default_store_path()
    return database.with_name(database.name + ".blobs")


def _register_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def _log_request(request: Request, call_next):
        response = await call_next(request)
        _LOG.info("%s %s -> %d", request.method, request.scope.get("path", ""),
                  response.status_code)
        return response


def create_app(shared_secret: Optional[str] = None,
               ttl_s: float = _DEFAULT_TTL_S,
               serve_web_viewer: bool = True,
               cors_origins: Optional[list] = None, *,
               config_store_path: str | Path | None = None,
               allow_blind_config_writes: bool = False,
               blob_store_path: str | Path | None = None,
               max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES,
               blob_quota_bytes: int = DEFAULT_BLOB_QUOTA_BYTES) -> FastAPI:
    """Build the FastAPI app. Importable for embedding in larger services.

    ``config_store_path`` is the SQLite file behind ``/config`` (default
    ``~/.je_auto_control/config_sync.sqlite3``); it is opened at the first
    ``/config`` request, not here. ``allow_blind_config_writes`` accepts the
    bare-bucket ``PUT`` of clients older than the version-2 envelope, which
    overwrites without a revision check.

    ``blob_store_path`` is the folder behind ``/blobs`` (default: the config
    database's path with ``.blobs`` added), created at the first upload.
    ``max_blob_bytes`` caps one blob and ``blob_quota_bytes`` what one
    account may hold in total.
    """
    app = FastAPI(title="AutoControl Signaling", version="1.0.0")
    store = _SessionStore(ttl_s=ttl_s)
    blobs = BlobStore(_blob_root(blob_store_path, config_store_path),
                      max_blob_bytes=max_blob_bytes, quota_bytes=blob_quota_bytes,
                      max_users=_MAX_CONFIG_USERS)
    # Before CORS, so CORS wraps it and a browser still sees the 401 / 413.
    _register_body_guard(app, shared_secret, blobs.max_blob_bytes)
    _configure_cors(app, cors_origins)
    _maybe_mount_viewer(app, serve_web_viewer)
    secret_dep = _build_secret_dependency(shared_secret)
    _register_routes(app, store, secret_dep)
    _register_config_routes(app, ConfigStore(config_store_path, max_users=_MAX_CONFIG_USERS),
                            secret_dep, allow_blind_config_writes)
    _register_blob_routes(app, blobs, secret_dep)
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
    parser.add_argument("--config-db", default=None,
                        help="SQLite file for config-sync buckets (default: "
                             "$AC_SIGNALING_CONFIG_DB, else "
                             "~/.je_auto_control/config_sync.sqlite3)")
    parser.add_argument("--allow-blind-config-writes", action="store_true",
                        help="accept the unconditional bucket PUT of clients older "
                             "than the version-2 envelope (no revision check: "
                             "concurrent pushes can overwrite each other)")
    parser.add_argument("--blob-dir", default=None,
                        help="folder for config-sync asset blobs (default: the "
                             "config database's path with .blobs added)")
    parser.add_argument("--max-blob-bytes", default=DEFAULT_MAX_BLOB_BYTES, type=int,
                        help="largest single blob accepted at /blobs "
                             f"(default: {DEFAULT_MAX_BLOB_BYTES})")
    parser.add_argument("--blob-quota-bytes", default=DEFAULT_BLOB_QUOTA_BYTES, type=int,
                        help="how much one account may store at /blobs in total "
                             f"(default: {DEFAULT_BLOB_QUOTA_BYTES})")
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
        config_store_path=args.config_db or os.environ.get("AC_SIGNALING_CONFIG_DB") or None,
        allow_blind_config_writes=args.allow_blind_config_writes,
        blob_store_path=args.blob_dir,
        max_blob_bytes=args.max_blob_bytes,
        blob_quota_bytes=args.blob_quota_bytes,
    )
    uvicorn.run(app, host=args.bind, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
