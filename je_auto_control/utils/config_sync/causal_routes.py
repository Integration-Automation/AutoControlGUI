"""Private version-three HTTP snapshots and actor-validated causal commits."""
from typing import Callable, cast

from fastapi import Depends, FastAPI, HTTPException

from je_auto_control.utils.config_sync.causal_store import CausalConfigStore, _parse_causal_request
from je_auto_control.utils.config_sync.contract import (
    ConfigRevisionConflict, ConfigStoreError, ConfigStoreFull, ConfigSyncError,
)
from je_auto_control.utils.config_sync.peers import FullResyncRequired
from je_auto_control.utils.config_sync.store import ConfigStore


def register_causal_routes(app: FastAPI, store: ConfigStore, secret_dep: Callable[..., object]) -> None:
    """Use a dedicated route so older servers cannot accept causal metadata as opaque legacy configuration."""
    causal = CausalConfigStore(store)
    auth = [Depends(secret_dep)]

    def get_causal(user_id: str) -> dict[str, object]:
        try:
            return {"version": 3, "bucket": causal.get(user_id).to_dict()}
        except ConfigSyncError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ConfigStoreError as error:
            raise HTTPException(status_code=503, detail="config storage unavailable") from error

    def put_causal(user_id: str, body: dict[str, object]) -> dict[str, object]:
        try:
            _envelope(body)
            bucket, actor = _parse_causal_request(cast(dict[str, object], body["bucket"]))
            revision = causal.commit(user_id, bucket, base_revision=cast(int, body["base_revision"]),
                                     operation_id=cast(str, body["operation_id"]), actor=actor)
            return {"version": 3, "revision": revision, "bucket": causal.get(user_id).to_dict()}
        except ConfigSyncError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ConfigRevisionConflict as error:
            raise HTTPException(status_code=409, detail={"message": str(error), "revision": error.current_revision,
                                                         "code": error.code}) from error
        except FullResyncRequired as error:
            detail = {"message": str(error), "code": "full_resync_required"}
            raise HTTPException(status_code=409, detail=detail) from error
        except (ConfigStoreFull, ConfigStoreError) as error:
            raise HTTPException(status_code=503, detail="config storage unavailable or full") from error

    app.add_api_route("/config/{user_id}/causal", get_causal, methods=["GET"], dependencies=auth)
    app.add_api_route("/config/{user_id}/causal", put_causal, methods=["PUT"], dependencies=auth)


def _envelope(body: dict[str, object]) -> None:
    if (set(body) != {"version", "base_revision", "operation_id", "bucket"}
            or not isinstance(body["version"], int) or isinstance(body["version"], bool)
            or body["version"] != 3 or not isinstance(body["bucket"], dict)):
        raise ConfigSyncError("invalid version-three causal envelope")
