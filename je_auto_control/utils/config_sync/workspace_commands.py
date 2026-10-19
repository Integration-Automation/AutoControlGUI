"""Route private workspace JSON operations through the same lazy coordinator and live path/cancellation authority."""
from dataclasses import asdict
from typing import Callable, Optional, cast

from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, KINDS
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.control_models import ControlKind, SyncControlRequest
from je_auto_control.utils.config_sync.workspace_sync import SyncWorkspace
from je_auto_control.utils.config_sync.workspace_transport import network_options
from je_auto_control.utils.config_sync.versions import _key_text
from je_auto_control.utils.path_guard import PathPolicy

_NETWORK = {'secret_env', 'timeout_s', 'policy', 'max_rebases'}
_CONTROLS = {'register', 'ack', 'retire', 'collect', 'full_resync'}
_FIELDS = {'status': set(), 'capture': set(), 'sync': _NETWORK, 'review': {'kind'},
           'resolve': {'kind', 'entry_id', 'value', 'observed', 'is_deleted'}, 'materialize': {'target_root'}}


def _sync_workspace(configuration: dict[str, object], operation: str = 'status',
                    options: Optional[dict[str, object]] = None, *, path_policy: Optional[PathPolicy] = None,
                    cancelled: Optional[Callable[[], bool]] = None) -> dict[str, object]:
    """Coordinate explicit local profiles; even local status requires private DRIVE authority at server boundaries."""
    settings, request = _arguments(operation, options)
    workspace = SyncWorkspace(configuration, path_policy=path_policy, cancelled=cancelled)
    if request is not None:
        return asdict(workspace.control(request, options={key: settings[key] for key in settings if key in _NETWORK}))
    if operation == 'status':
        return workspace.status()
    if operation == 'capture':
        return {'captured': workspace.capture()}
    if operation == 'sync':
        return asdict(workspace.synchronize(options=settings))
    return _profile_operation(workspace, operation, settings)


def _profile_operation(workspace: SyncWorkspace, operation: str, settings: dict[str, object]) -> dict[str, object]:
    if operation == 'materialize':
        result = workspace.materialize(cast(str, settings['target_root']))
        return dict(asdict(result), directory=str(result.directory))
    kind = cast(AdapterKind, settings['kind'])
    if operation == 'review':
        return {'kind': kind, 'entries': {key: entry.to_dict() for key, entry in workspace.review(kind).items()}}
    return workspace.resolve(kind, cast(str, settings['entry_id']), cast(dict[str, object], settings['value']),
        observed=cast(list[str], settings['observed']),
        is_deleted=cast(bool, settings.get('is_deleted', False))).to_dict()


def _arguments(operation: str, options: Optional[dict[str, object]]
               ) -> tuple[dict[str, object], SyncControlRequest | None]:
    settings = _settings(operation, options)
    if operation in _CONTROLS:
        network_options({key: settings[key] for key in settings if key in _NETWORK})
        request = SyncControlRequest(cast(ControlKind, operation), cast(Optional[str], settings.get('operation_id')),
            cast(Optional[str], settings.get('peer_id')), cast(bool, settings.get('discard_pending', False)))
        return settings, request
    if operation == 'sync':
        network_options(settings)
    _local_arguments(operation, settings)
    return settings, None


def _settings(operation: str, options: Optional[dict[str, object]]) -> dict[str, object]:
    if not isinstance(operation, str) or operation not in set(_FIELDS) | _CONTROLS:
        raise ConfigSyncError('unknown workspace operation')
    allowed = (_NETWORK | {'operation_id', 'peer_id', 'discard_pending'}
               if operation in _CONTROLS else _FIELDS[operation])
    if options is not None and (not isinstance(options, dict) or not set(options) <= allowed):
        raise ConfigSyncError('invalid workspace operation options')
    return dict(options or {})


def _local_arguments(operation: str, settings: dict[str, object]) -> None:
    if operation == 'materialize':
        target = settings.get('target_root')
        if not isinstance(target, str) or not target.strip():
            raise ConfigSyncError('workspace materialization requires an explicit target_root')
    if operation in {'review', 'resolve'}:
        if not isinstance(settings.get('kind'), str) or settings['kind'] not in KINDS:
            raise ConfigSyncError('workspace review/resolution requires a selected kind')
    if operation == 'resolve':
        _resolution_arguments(settings)


def _resolution_arguments(settings: dict[str, object]) -> None:
    _key_text(cast(str, settings.get('entry_id')))
    observed = settings.get('observed')
    if (not isinstance(settings.get('value'), dict) or not isinstance(observed, list)
            or not 1 <= len(observed) <= 128 or not all(isinstance(item, str) for item in observed)
            or not isinstance(settings.get('is_deleted', False), bool)):
        raise ConfigSyncError('workspace resolution requires value/observed and an optional deletion flag')
