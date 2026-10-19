"""Bind causal definitions to immutable asset uploads and durable profile downloads under live authority."""
from dataclasses import dataclass
from typing import Callable, Iterable, cast

from je_auto_control.utils.config_sync.adapter_ledger import fingerprint
from je_auto_control.utils.config_sync.blob_binding import asset_references
from je_auto_control.utils.config_sync.blob_http import SyncAssetHTTPClient
from je_auto_control.utils.config_sync.blob_models import SyncAssetReference
from je_auto_control.utils.config_sync.blob_store import SyncAssetStore
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.outbox_models import SyncOperation
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.config_sync.workspace_config import WorkspaceSpec
from je_auto_control.utils.config_sync.workspace_models import SyncWorkspaceError, validate_workspace_snapshot


@dataclass(frozen=True)
class WorkspaceHTTPContext:
    """Private per-drain capabilities retain no plaintext credential and open the cache only for actual references."""

    spec: WorkspaceSpec
    options: dict[str, object]
    checkpoint: Callable[[], None]

    @property
    def user_id(self) -> str:
        """Match adapter-cache scope without pinning bytes to an obsolete peer epoch."""
        return fingerprint({'endpoint': self.spec.endpoint, 'user_id': self.spec.user_id})

    def _poll(self) -> bool:
        self.checkpoint()
        return False

    def _client(self) -> SyncAssetHTTPClient:
        return SyncAssetHTTPClient(self.spec.endpoint, user_id=self.spec.user_id,
            secret_env=cast(str | None, self.options.get('secret_env')),
            timeout_s=cast(float, self.options.get('timeout_s', 5.0)), cancelled=self._poll)

    def upload(self, operation: SyncOperation) -> None:
        """Upload only current logical references before preparing any new causal edit request."""
        self.checkpoint()
        validate_workspace_snapshot(CausalBucket(self.spec.user_id, entries=operation.entries))
        references = _references(operation.entries)
        if not references:
            return
        store = SyncAssetStore(self.spec.asset_cache_path)
        client = self._client()
        for item in references:
            self.checkpoint()
            if not store.contains(self.user_id, item.blob):
                if client.probe(item.blob)[0]:
                    continue
                raise SyncWorkspaceError('queued definition asset is missing from its frozen cache',
                                         code='missing_asset')
            client.upload(item.blob, store, self.user_id)

    def download(self, entries: Iterable[SyncEntry]) -> None:
        """Download selected live heads, retaining partial chunks across cancellation or connection loss."""
        references = _references(entries)
        if not references:
            return
        store = SyncAssetStore(self.spec.asset_cache_path)
        client = self._client()
        for item in references:
            self.checkpoint()
            if not store.contains(self.user_id, item.blob):
                client.download(item.blob, store, self.user_id)


def _references(entries: Iterable[SyncEntry]) -> tuple[SyncAssetReference, ...]:
    values = {item for entry in entries if not entry.is_deleted for item in asset_references(entry.value)}
    return tuple(sorted(values, key=lambda item: (item.blob.sha256, item.path)))
