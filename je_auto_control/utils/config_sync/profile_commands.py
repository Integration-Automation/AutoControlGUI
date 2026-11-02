"""Private native-profile loading commands share exact manifest review and current path/cancellation authority."""
from typing import Callable, Optional

from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.profile_load import load_sync_profile
from je_auto_control.utils.path_guard import PathPolicy


def profile_parameters(options: dict[str, object]) -> tuple[str, str, str]:
    """Validate one explicit native load form without consulting a source, credential or database."""
    if not isinstance(options, dict) or set(options) != {'directory', 'target_root', 'expected_digest'}:
        raise ConfigSyncError('native loading requires directory, target_root and expected_digest')
    result = []
    for name in ('directory', 'target_root', 'expected_digest'):
        value = options[name]
        if not isinstance(value, str) or not value.strip() or not value.isprintable() or len(value) > 4096:
            raise ConfigSyncError('native load fields require bounded printable text')
        result.append(value)
    return result[0], result[1], result[2]


def _load_sync_profile(directory: str, target_root: str, expected_digest: str, *,
                          path_policy: Optional[PathPolicy] = None,
                          cancelled: Optional[Callable[[], bool]] = None) -> dict[str, object]:
    """Load one completely verified native working snapshot without registering or enabling received work."""
    paths = profile_parameters({'directory': directory, 'target_root': target_root, 'expected_digest': expected_digest})
    return load_sync_profile(paths[0], paths[1], expected_digest=paths[2],
                              path_policy=path_policy, cancelled=cancelled).to_dict()
