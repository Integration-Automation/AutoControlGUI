"""Cheap workspace/asset network option validation resolves no credential and opens no connection."""
import math
import re
from typing import Optional

from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.http_commands import _options, _retry_policy


def network_options(value: Optional[dict[str, object]]) -> dict[str, object]:
    """Validate cheap option grammar without resolving a credential or opening a connection."""
    result = _options(value, ('policy', 'max_rebases'))
    _timeout(result.get('timeout_s', 5.0))
    _credential(result.get('secret_env'))
    _rebases(result.get('max_rebases', 3))
    _retry_policy(result.get('policy'))
    return result


def _timeout(timeout: object) -> None:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
        raise ConfigSyncError('workspace timeout must be a finite positive number up to 300 seconds')
    if not math.isfinite(timeout):
        raise ConfigSyncError('workspace timeout must be finite')

def _credential(environment: object) -> None:
    if environment is not None and (not isinstance(environment, str)
                                   or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', environment) is None):
        raise ConfigSyncError('secret_env must name one environment variable')

def _rebases(rebases: object) -> None:
    if isinstance(rebases, bool) or not isinstance(rebases, int) or not 0 <= rebases <= 10:
        raise ConfigSyncError('workspace rebasing allows 0–10 definite stale-base retries')
