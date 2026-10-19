"""Resumable asset HTTP reuses bounded egress, refreshes live credentials and preserves cancellation."""
from __future__ import annotations

from concurrent.futures import CancelledError
import os
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.blob_codec import decode_chunk, encode_chunk
from je_auto_control.utils.config_sync.blob_models import SyncAssetBlob
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
from je_auto_control.utils.config_sync.client import ConfigSyncClient
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded, _identifier, _schema_one
from je_auto_control.utils.config_sync.http_commands import _client
from je_auto_control.utils.config_sync.outbox_models import normalize_sync_endpoint
from je_auto_control.utils.config_sync.workspace_models import SyncWorkspaceError
from je_auto_control.utils.config_sync.workspace_options import network_options
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.logging.secret_scope import remember_secret, scrub_secret_text, secret_log_scope


class _AssetWire(ConfigSyncClient):
    """A per-RPC shared transport preserves no-redirect egress and bounded response handling."""

    def __init__(self, endpoint: str, user_id: str, secret: Optional[str], timeout: float, suffix: str) -> None:
        super().__init__(endpoint, user_id=user_id, secret=secret, timeout_s=timeout)
        self._suffix = suffix

    def _request_endpoint(self, method: str) -> str:
        return self._endpoint('/assets' + self._suffix)

    def request(self, method: str, body: Optional[dict[str, object]]) -> dict[str, object]:
        """Reject older routes, oversized protocol JSON and malformed replies without echoing remote payloads."""
        try:
            reply = self._request(method, body=body)
        except ConfigSyncError as error:
            raise_caused_run_interruption(error)
            raise ConfigSyncError(scrub_secret_text(str(error))) from None
        if not isinstance(reply, dict) or not _schema_one(reply.get('version')):
            raise ConfigSyncError('server did not confirm the version-one asset protocol')
        _encoded(reply)
        return cast(dict[str, object], reply)


class SyncAssetHTTPClient:
    """Upload/download complete verified blobs with bounded RAM and restartable immutable per-account chunks."""

    def __init__(self, server_url: str, *, user_id: str, secret_env: Optional[str] = None,
                   timeout_s: float = 5.0, cancelled: Optional[Callable[[], bool]] = None) -> None:
        self._endpoint = normalize_sync_endpoint(server_url)
        _identifier(user_id, 'asset user_id')
        self._user_id = user_id
        self._options = network_options({'secret_env': secret_env, 'timeout_s': timeout_s})
        self._cancelled = cancelled

    def _check(self) -> None:
        if self._cancelled is not None and self._cancelled():
            raise CancelledError()

    def _call(self, method: str, suffix: str, body: Optional[dict[str, object]] = None) -> dict[str, object]:
        self._check()
        with secret_log_scope():
            delegate = _client(self._endpoint, self._user_id, self._options)
            # pylint: disable-next=protected-access  # reason: reuse the package's live environment credential resolution without retaining plaintext options
            secret = delegate._secret
            remember_secret(secret or '')
            wire = _AssetWire(self._endpoint, self._user_id, secret,
                               cast(float, self._options.get('timeout_s', 5.0)), suffix)
            try:
                return wire.request(method, body)
            finally:
                environment = self._options.get('secret_env')
                if isinstance(environment, str):
                    remember_secret(os.environ.get(environment, ''))

    def probe(self, blob: SyncAssetBlob) -> tuple[bool, tuple[str, ...]]:
        """Inspect one complete receipt/missing hash set; untrusted reply values cannot reach local storage."""
        self._check()
        if not isinstance(blob, SyncAssetBlob):
            raise ConfigSyncError('asset probe requires a typed blob descriptor')
        reply = self._call('POST', '/probe', {'version': 1, 'blob': blob.to_dict()})
        if set(reply) != {'version', 'complete', 'missing'} or not isinstance(reply['complete'], bool):
            raise _invalid_reply()
        missing = _missing_reply(reply['missing'], blob)
        if reply['complete'] and missing:
            raise _invalid_reply()
        return reply['complete'], missing

    def upload(self, blob: SyncAssetBlob, source: SyncAssetStore, source_user: str) -> bool:
        """Publish missing chunks before the whole receipt; accepted uncertain chunks need no retransmission."""
        self._check()
        if not source.contains(source_user, blob):
            raise ConfigSyncError('local asset blob is unavailable')
        complete, missing = self.probe(blob)
        if complete:
            return False
        for digest in missing:
            self._check()
            body = source.read_chunk(source_user, digest)
            _stored(self._call('PUT', '/chunks/' + digest, {'version': 1, 'data': encode_chunk(body)}))
        _stored(self._call('PUT', '/blobs/' + blob.sha256, {'version': 1, 'blob': blob.to_dict()}))
        return True

    def download(self, blob: SyncAssetBlob, target: SyncAssetStore, target_user: str) -> bool:
        """Keep downloaded chunks durable, but publish a local blob only after the complete full hash verifies."""
        self._check()
        complete, _missing = self.probe(blob)
        if not complete:
            raise ConfigSyncError('remote asset blob is unavailable')
        if target.contains(target_user, blob):
            return False
        for digest in target.missing_chunks(target_user, blob):
            self._check()
            reply = self._call('GET', '/chunks/' + digest)
            if set(reply) != {'version', 'data'}:
                raise _invalid_reply()
            body = decode_chunk(reply['data'])
            self._check()
            target.put_chunk(target_user, digest, body)
        target.commit(target_user, blob)
        return True


def _invalid_reply() -> SyncWorkspaceError:
    return SyncWorkspaceError('invalid asset protocol reply', code='invalid_asset_reply')


def _stored(reply: dict[str, object]) -> bool:
    if set(reply) != {'version', 'stored'} or not isinstance(reply['stored'], bool):
        raise _invalid_reply()
    return reply['stored']


def _missing_reply(value: object, blob: SyncAssetBlob) -> tuple[str, ...]:
    if (not isinstance(value, list) or len(value) > len(blob.chunks)
            or not all(isinstance(item, str) for item in value)):
        raise _invalid_reply()
    if len(set(value)) != len(value) or not set(value) <= set(blob.chunks):
        raise _invalid_reply()
    return tuple(value)
