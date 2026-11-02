"""Match native generation values to exact portable heads and rebind verified asset references to a working root."""
from copy import deepcopy
from pathlib import Path
from typing import Optional, cast

from je_auto_control.utils.config_sync.adapter_references import _reference
from je_auto_control.utils.config_sync.asset_commands import _root
from je_auto_control.utils.config_sync.asset_models import AssetFile, AssetManifest
from je_auto_control.utils.config_sync.blob_binding import asset_reference
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.path_guard import PathPolicy


class ProfileBindings:
    """Bind only explicit asset references and native path fields after exact portable/native comparison."""

    def __init__(self, root: Path, manifest: AssetManifest, policy: Optional[PathPolicy]) -> None:
        self._root = root
        self._files: dict[str, AssetFile] = {item.path: item for item in manifest.files}
        self._policy = policy
        self.assets: set[str] = set()

    def value(self, portable: object, native: object, depth: int = 0) -> object:
        """Match literal types/shapes, preserve secret placeholders and rebase exact verified asset markers."""
        if depth > 32:
            raise ConfigSyncError('loaded profile values exceed the nesting limit')
        asset = asset_reference(portable)
        if asset is not None:
            if native != asset.path or self._files.get(asset.path) != asset.file:
                raise ConfigSyncError('native asset path or content differs from the reviewed reference')
            self.assets.add(asset.path)
            return self.path(asset.path)
        reference = _reference(portable)
        if reference is not None:
            if reference.kind == 'secret':
                if native != '${secrets.' + reference.name + '}':
                    raise ConfigSyncError('loaded secrets must remain unresolved interpolation placeholders')
            elif _unresolved(native):
                raise ConfigSyncError('native local bindings must be completely resolved')
            return deepcopy(native)
        return self._literal(portable, native, depth)

    def _literal(self, portable: object, native: object, depth: int) -> object:
        if isinstance(portable, dict):
            if not isinstance(native, dict) or set(portable) != set(native):
                raise ConfigSyncError('native profile fields differ from their portable heads')
            return {key: self.value(value, native[key], depth + 1) for key, value in portable.items()}
        if isinstance(portable, list):
            if not isinstance(native, list) or len(portable) != len(native):
                raise ConfigSyncError('native profile arrays differ from their portable heads')
            return [self.value(value, native[index], depth + 1) for index, value in enumerate(portable)]
        if _encoded({'value': portable}) != _encoded({'value': native}):
            raise ConfigSyncError('native profile literals differ from their reviewed values')
        return native

    def path(self, value: str) -> str:
        """Resolve a private native file/condition path against the selected working root with live root checks."""
        if not value:
            return value
        path = Path(value).expanduser()
        candidate = path if path.is_absolute() else self._root / path
        resolved = _root(candidate, self._policy)
        if not path.is_absolute() and not resolved.is_relative_to(self._root):
            raise ConfigSyncError('native relative paths must stay inside the loaded workspace')
        return str(resolved)

    def native_paths(self, kind: str, value: dict[str, object]) -> dict[str, object]:
        """Rebase native hotkey/trigger paths without interpreting arbitrary script argument strings."""
        if kind not in {'hotkeys', 'triggers'}:
            return value
        result = dict(value)
        result['script_path'] = self.path(cast(str, value['script_path']))
        if kind == 'triggers':
            if 'children' in value:
                result['children'] = [self.native_paths('triggers', child)
                                      for child in cast(list[dict[str, object]], value['children'])]
            else:
                condition = dict(cast(dict[str, object], value['condition']))
                for field in {'watch_path', 'image_path'} & condition.keys():
                    condition[field] = self.path(cast(str, condition[field]))
                result['condition'] = condition
        return result


def _unresolved(value: object, depth: int = 0) -> bool:
    if depth > 32:
        raise ConfigSyncError('native local binding exceeds the nesting limit')
    if _reference(value) is not None or asset_reference(value) is not None:
        return True
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return any(_unresolved(item, depth + 1) for item in items)
