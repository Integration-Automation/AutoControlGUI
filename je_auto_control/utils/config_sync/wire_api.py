"""JSON-only command adapters over cancellable Python services."""
from typing import Any, Dict, Mapping, Union

from . import service
from .asset_service import config_sync_assets as _assets
from .service import config_sync_status


# Empty means no configured credential; it is not a built-in password.
def config_sync_preview(  # nosec B107
    definitions_path: str, workspace_path: str, server_url: str, user_id: str,
    shared_secret: str = '') -> Dict[str, Any]:
    """Preview definitions without applying or publishing; persist portable causal state."""
    return service.config_sync_preview(definitions_path, workspace_path, server_url, user_id, shared_secret)


# Empty means no configured credential; it is not a built-in password.
def config_sync_exchange(  # nosec B107
    definitions_path: str, workspace_path: str, server_url: str, user_id: str,
    shared_secret: str = '') -> Dict[str, Any]:
    """Publish protected definitions while retaining explicit local application."""
    return service.config_sync_exchange(definitions_path, workspace_path, server_url, user_id, shared_secret)


def config_sync_apply(definitions_path: str, preview_path: str, state_path: str, device_id: str, *,
                      choices: Union[Mapping[str, int], str] = '{}') -> Dict[str, Any]:
    """Apply selected preview entries with baseline and asset integrity checks."""
    return service.config_sync_apply(definitions_path, preview_path, state_path, device_id, choices=choices)


# Empty means no configured credential; it is not a built-in password.
def config_sync_retry(  # nosec B107
    workspace_path: str, server_url: str, user_id: str,
    shared_secret: str = '') -> Dict[str, Any]:
    """Retry durable envelopes with finite attempts and retained uncertain identities."""
    return service.config_sync_retry(workspace_path, server_url, user_id, shared_secret)


def config_sync_assets(manifest_path: str, source_root: str, destination_root: str) -> Dict[str, Any]:
    """Publish completed assets after exact size and SHA256 verification."""
    return _assets(manifest_path, source_root, destination_root)


__all__ = ['config_sync_preview', 'config_sync_exchange', 'config_sync_apply',
           'config_sync_retry', 'config_sync_status', 'config_sync_assets']
