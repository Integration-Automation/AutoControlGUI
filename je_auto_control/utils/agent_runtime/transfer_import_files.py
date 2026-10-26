"""Verified import chunks and owned generations reuse existing asset publication and verification."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import TransferManifest
from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest, AssetSyncResult
from je_auto_control.utils.config_sync.assets import _sync_assets, _verified_result
from je_auto_control.utils.agent_runtime.transfer_staging import ImportStaging, cleanup_staging


def _assets(manifest: TransferManifest) -> AssetManifest:
    return AssetManifest(tuple(AssetFile(item.name, item.blob.sha256, item.blob.size) for item in manifest.files))


def publication_root(record: dict, publication: dict) -> Path:
    """Require the exact host-derived directory and persisted filesystem identity before inspecting bytes."""
    root = Path(record['scope']['destination']['directory']) / ('import-' + record['id'])
    if publication.get('root') != str(root) or publication.get('phase') not in {'owned', 'verified'}:
        raise AgentTaskError('destination publication ownership requires review')
    identity = root.stat()
    if root.resolve() != root or publication.get('identity') != [identity.st_dev, identity.st_ino]:
        raise AgentTaskError('destination publication directory identity changed')
    return root


def retire_import_staging(record: dict, publication: dict) -> dict | None:
    """Retire a journaled allocation without touching published generations or unrelated output."""
    if not publication or publication.get('phase') == 'preparing':
        return None
    root = publication_root(record, publication)
    witness = publication.get('staging')
    if witness is None:
        if any(path.name.startswith('.incoming-') for path in root.iterdir()):
            raise AgentTaskError('unjournaled import staging requires review before releasing capacity')
        return None
    cleanup_staging(root, publication['identity'], witness)
    return witness


def inspect_import(record: dict, manifest: TransferManifest, publication: dict,
                   check: Callable[[], None]) -> AssetSyncResult:
    """Hash an owned existing generation through the shared validator without creating, deleting or publishing files."""
    root, assets = publication_root(record, publication), _assets(manifest)
    def cancelled() -> bool:
        check()
        publication_root(record, publication)
        return False
    result = _verified_result(root / ('generation-' + assets.digest), assets, True, cancelled)
    check()
    return result


@dataclass(frozen=True)
class ImportAssetTransport:
    """A host-derived account supplies only manifest-selected, independently reverified cached blobs."""

    target_root: Path
    manifest: TransferManifest
    cache: Any
    account: str

    def open(self, asset: AssetFile) -> BinaryIO:
        """Read an exact blob descriptor; sync_assets independently checks every streamed byte again."""
        selected = next(item for item in self.manifest.files if item.name == asset.path)
        self.cache.check()
        return self.cache.store.open(self.account, selected.blob)


def receive_chunks(record: dict, manifest: TransferManifest, cache: Any, read: Callable,
                   check: Callable[[], None]) -> None:
    """Commit bounded content-addressed blobs only after current authority is rechecked around every cache effect."""
    for item in manifest.files:
        check()
        cache.check()
        for digest in cache.store.missing_chunks(record['account'], item.blob):
            check()
            reply = read(digest)
            check()
            cache.check()
            cache.store.put_chunk(record['account'], digest, base64.b64decode(reply['data'], validate=True))
            check()
        cache.check()
        cache.store.commit(record['account'], item.blob)
        check()


def publish_import(record: dict, manifest: TransferManifest, cache: Any, check: Callable[[], None],
                   record_publication: Callable[[dict], None],
                   stage_retired: Callable[[dict], None] | None = None) -> AssetSyncResult:
    """Use an exclusive per-import directory and the established generation layout without replacing user output."""
    directory = Path(record['scope']['destination']['directory'])
    root = directory / ('import-' + record['id'])
    publication: dict[str, Any] = {'root': str(root), 'phase': 'preparing'}
    check()
    record_publication(publication)
    directory.mkdir(parents=True, exist_ok=True)
    check()
    root.mkdir(exist_ok=False)
    identity = root.stat()
    publication.update(phase='owned', identity=[identity.st_dev, identity.st_ino])
    check()
    record_publication(publication)
    assets = _assets(manifest)
    def cancelled() -> bool:
        check()
        if root.resolve() != root or [root.stat().st_dev, root.stat().st_ino] != publication['identity']:
            raise AgentTaskError('owned import publication directory changed')
        return False
    def staged(witness: dict) -> None:
        publication['staging'] = witness
        record_publication(publication)
    def retired(witness: dict) -> None:
        publication['staging'] = {**witness, 'cleaned': True}
        if stage_retired is not None:
            stage_retired(witness)
    result = _sync_assets(assets, ImportAssetTransport(root, manifest, cache, record['account']),
                          cancelled=cancelled, staging=ImportStaging(root, publication['identity'], staged, retired))
    check()
    publication.update(phase='verified', files_directory=str(result.directory), asset_digest=result.manifest_digest)
    record_publication(publication)
    return result
