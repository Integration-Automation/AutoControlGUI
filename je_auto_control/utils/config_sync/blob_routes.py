"""Authenticated bounded asset routes expose account-isolated chunks and complete hash-verified blob receipts."""
from typing import Callable, cast

from fastapi import Depends, FastAPI, HTTPException

from je_auto_control.utils.config_sync.blob_codec import decode_chunk, encode_chunk
from je_auto_control.utils.config_sync.blob_models import SyncAssetBlob
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigStoreFull, ConfigSyncError, _schema_one


def register_asset_routes(app: FastAPI, store: SyncAssetStore, secret_dep: Callable[..., object]) -> None:
    """Register under /config so the existing pre-body authentication/one-MiB guard applies to every upload."""
    auth = [Depends(secret_dep)]

    def probe(user_id: str, body: dict[str, object]) -> dict[str, object]:
        """Query exact complete status and missing chunks without publishing a descriptor."""
        def operation() -> dict[str, object]:
            blob = _blob_body(body)
            return {'version': 1, 'complete': store.contains(user_id, blob),
                    'missing': list(store.missing_chunks(user_id, blob))}
        return _route(operation)

    def put_chunk(user_id: str, digest: str, body: dict[str, object]) -> dict[str, object]:
        """Verify the bounded chunk content address before account quota admission."""
        def operation() -> dict[str, object]:
            _envelope(body, 'data')
            return {'version': 1, 'stored': store.put_chunk(user_id, digest, decode_chunk(body['data']))}
        return _route(operation)

    def get_chunk(user_id: str, digest: str) -> dict[str, object]:
        """Read only one verified account-owned chunk, never another account's matching content address."""
        return _route(lambda: {'version': 1, 'data': encode_chunk(store.read_chunk(user_id, digest))})

    def commit(user_id: str, digest: str, body: dict[str, object]) -> dict[str, object]:
        """Publish only a complete whole-hash receipt; accepted chunk retries remain idempotent."""
        def operation() -> dict[str, object]:
            blob = _blob_body(body)
            if blob.sha256 != digest:
                raise ConfigSyncError('asset URL and content descriptor hashes differ')
            return {'version': 1, 'stored': store.commit(user_id, blob)}
        return _route(operation)

    app.add_api_route('/config/{user_id}/assets/probe', probe, methods=['POST'], dependencies=auth)
    app.add_api_route('/config/{user_id}/assets/chunks/{digest}', put_chunk, methods=['PUT'], dependencies=auth)
    app.add_api_route('/config/{user_id}/assets/chunks/{digest}', get_chunk, methods=['GET'], dependencies=auth)
    app.add_api_route('/config/{user_id}/assets/blobs/{digest}', commit, methods=['PUT'], dependencies=auth)


def _route(operation: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return operation()
    except ConfigSyncError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (ConfigStoreError, ConfigStoreFull) as error:
        raise HTTPException(status_code=503, detail='asset storage unavailable or full') from error


def _envelope(body: dict[str, object], field: str) -> None:
    if not isinstance(body, dict) or set(body) != {'version', field} or not _schema_one(body['version']):
        raise ConfigSyncError('invalid version-one asset request')


def _blob_body(body: dict[str, object]) -> SyncAssetBlob:
    _envelope(body, 'blob')
    return SyncAssetBlob.from_dict(cast(dict[str, object], body['blob']))
