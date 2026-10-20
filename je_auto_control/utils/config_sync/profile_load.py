"""Load an explicitly reviewed immutable generation into a separate native working copy with no runtime activation."""
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Callable, Optional, cast
from uuid import uuid4

from je_auto_control.utils.config_sync.asset_commands import _checkpoint, _root
from je_auto_control.utils.config_sync.asset_models import AssetManifest
from je_auto_control.utils.config_sync.assets import _copy_stream, _source_file, _verified_result
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.profile_models import LoadedSyncProfile
from je_auto_control.utils.config_sync.profile_native import native_profile
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.path_guard import PathPolicy


def load_sync_profile(directory: str | Path, target_root: str | Path, *, expected_digest: str,
                         path_policy: Optional[PathPolicy] = None,
                         cancelled: Optional[Callable[[], bool]] = None) -> LoadedSyncProfile:
    """Verify a published files directory and create a fresh editable native snapshot; no engines or scripts start."""
    if not isinstance(expected_digest, str) or re.fullmatch('[0-9a-f]{64}', expected_digest) is None:
        raise ConfigSyncError('native loading requires the exact reviewed manifest digest')
    _checkpoint((), path_policy, cancelled)
    source, target = _root(_load_path(directory), path_policy), _root(_load_path(target_root), path_policy)
    generation = source.parent
    if source.name != 'files' or target.is_relative_to(generation):
        raise ConfigSyncError('working copy must be separate from the immutable generation')

    def checkpoint() -> bool:
        return _checkpoint((source, generation, target), path_policy, cancelled)

    try:
        manifest = _manifest(generation, expected_digest)
        _verified_result(generation, manifest, True, checkpoint)
        checkpoint()
        target.mkdir(parents=True, exist_ok=True)
        return _working_copy(source, target, manifest, path_policy, checkpoint)
    except (OSError, ValueError, TypeError) as error:
        raise_caused_run_interruption(error)
        raise ConfigSyncError('could not load a complete native working profile') from error


def _load_path(value: str | Path) -> str:
    if not isinstance(value, (str, Path)):
        raise ConfigSyncError('native load paths require text or Path values')
    text = str(value)
    if not text.strip() or not text.isprintable() or len(text) > 4096:
        raise ConfigSyncError('native load paths require bounded printable text')
    return text


def _working_copy(source: Path, target: Path, manifest: AssetManifest, policy: Optional[PathPolicy],
                     checkpoint: Callable[[], bool]) -> LoadedSyncProfile:
    destination = target / ('workspace-' + uuid4().hex)
    with TemporaryDirectory(prefix='.sync-profile-', dir=target) as temporary:
        staging = Path(temporary)
        _copy_files(source, staging, manifest, checkpoint)
        records, replacements = native_profile(staging, manifest, destination, policy)
        for name, body in replacements.items():
            checkpoint()
            (staging / name).write_bytes(body)
        receipt = {'schema_version': 1, 'source_manifest': manifest.to_dict(), 'manifest_digest': manifest.digest}
        (staging / '.sync-profile.json').write_bytes(_encoded(receipt).encode('ascii'))
        loaded = LoadedSyncProfile(destination, manifest.digest, records, path_policy=policy)
        checkpoint()
        _root(destination, policy)
        if destination.exists() or destination.is_symlink():
            raise ConfigSyncError('loaded working-copy destination already exists')
        staging.rename(destination)
    return loaded


def _manifest(generation: Path, expected: str) -> AssetManifest:
    path = generation / 'manifest.json'
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ConfigSyncError('native generation has no bounded manifest')
    manifest = AssetManifest.from_dict(cast(dict[str, object], json.loads(path.read_text(encoding='utf-8'))))
    if manifest.digest != expected:
        raise ConfigSyncError('native generation changed after manifest review')
    return manifest


def _copy_files(source: Path, target: Path, manifest: AssetManifest, checkpoint: Callable[[], bool]) -> None:
    for asset in manifest.files:
        checkpoint()
        destination = target / asset.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _source_file(source, asset).open('rb') as stream:
            _copy_stream(stream, asset, destination, checkpoint)
