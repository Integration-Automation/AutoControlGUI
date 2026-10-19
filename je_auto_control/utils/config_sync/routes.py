"""Authenticated version-two configuration commits on the optional signaling server."""
from typing import Callable, cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _version_two
from je_auto_control.utils.config_sync.store import (
    ConfigRevisionConflict, ConfigStore, ConfigStoreError, ConfigStoreFull, _identifier, _parse_bucket,
)

_RESPONSES = {
    400: {"description": "invalid config envelope or account"},
    401: {"description": "bad shared secret"},
    404: {"description": "no bucket"},
    409: {"description": "stale revision or conflicting operation ID"},
    413: {"description": "request body too large"},
    428: {"description": "version-two conditional commit required"},
    503: {"description": "config storage unavailable or full"},
}


def register_config_routes(app: FastAPI, store: ConfigStore, secret_dep: Callable[..., object], *,
                           allow_legacy_writes: bool = False) -> None:
    """Register private bucket reads and CAS writes; database access stays lazy until an authorized request."""
    auth = [Depends(secret_dep)]

    @app.get("/config/{user_id}", responses=_RESPONSES, dependencies=auth)
    def get_config(user_id: str, response: Response) -> dict[str, object]:
        try:
            body = store.get_document(user_id)
        except ConfigSyncError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ConfigStoreError as error:
            raise HTTPException(status_code=503, detail="config storage unavailable") from error
        if body is None:
            raise HTTPException(status_code=404, detail="no bucket")
        response.headers["X-Autocontrol-Config-Protocol"] = "2"
        response.headers["X-Autocontrol-Config-CAS"] = "legacy-enabled" if allow_legacy_writes else "required"
        return body

    @app.put("/config/{user_id}", responses=_RESPONSES, dependencies=auth)
    @app.put("/config/{user_id}/commit", responses=_RESPONSES, dependencies=auth)
    def put_config(user_id: str, body: dict[str, object], request: Request) -> dict[str, object]:
        try:
            _identifier(user_id, "user_id")
            legacy = allow_legacy_writes and request.scope["path"] == f"/config/{user_id}"
            revision = _commit(store, user_id, body, legacy)
        except ConfigSyncError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ConfigRevisionConflict as error:
            raise HTTPException(status_code=409, detail={"message": str(error),
                                                         "revision": error.current_revision}) from error
        except (ConfigStoreFull, ConfigStoreError) as error:
            raise HTTPException(status_code=503, detail="config storage unavailable or full") from error
        return {"ok": True, "version": 2, "revision": revision}


def _commit(store: ConfigStore, user_id: str, body: dict[str, object], legacy: bool) -> int:
    if "version" not in body:
        if body.get("user_id", user_id) != user_id:
            raise ConfigSyncError("bucket user_id mismatch")
        if not legacy:
            raise HTTPException(status_code=428, detail="version-two conditional commit required")
        return store.put_legacy(user_id, body)
    if (not _version_two(body["version"])
            or set(body) != {"version", "base_revision", "operation_id", "bucket"}):
        raise ConfigSyncError("invalid version-two config envelope")
    bucket = body["bucket"]
    if not isinstance(bucket, dict):
        raise ConfigSyncError("bucket must be an object")
    return store.commit(user_id, _parse_bucket(bucket),
                        base_revision=cast(int, body["base_revision"]),
                        operation_id=cast(str, body["operation_id"]))
