"""Platform-checked mobile aliases and validated device-only action batches."""
from __future__ import annotations

from copy import deepcopy
from inspect import signature
from typing import Any, Iterable, Mapping, Optional, TYPE_CHECKING, cast

from je_auto_control.wrapper._mobile_models import DeviceSessionError
from je_auto_control.wrapper.mobile_actions import _owner
from je_auto_control.wrapper.mobile_surfaces import mobile_surface_matrix

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession
    from je_auto_control.utils.executor.action_executor import Executor


def _operation_parameters(operation: str, options: Mapping[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(options, Mapping) or 'device' in options:
        raise DeviceSessionError('mobile options must be an object without a device override')
    params = dict(options)
    if operation in ('launch_app', 'wait_for_app', 'app_state', 'stop_app'):
        if 'action' in params:
            raise DeviceSessionError('app action is determined by the selected operation')
        params['action'] = row['options']['action']
    elif operation in ('install', 'files', 'clipboard', 'recording'):
        params = {'operation': operation, 'options': params}
    return params


def _dispatch_service(api: str, params: dict[str, Any]) -> Any:
    # pylint: disable-next=import-outside-toplevel  # reason: selected headless services stay lazy in metadata imports
    from je_auto_control.wrapper import mobile_actions, mobile_setup
    module = mobile_setup if api == 'mobile_setup' else mobile_actions
    handler = getattr(module, api)
    try:
        signature(handler).bind(**params)
    except TypeError as failure:
        raise DeviceSessionError('mobile operation options do not match its service schema') from failure
    return handler(**params)


def _platform_action(platform: str, operation: str, options: Mapping[str, Any],
                     device: Optional[Mapping[str, Any]]) -> Any:
    row = next((entry for entry in mobile_surface_matrix(False)['operations'] if entry['operation'] == operation), None)
    if row is None:
        raise DeviceSessionError('unknown mobile operation')
    params = _operation_parameters(operation, options, row)
    with _owner(device) as bound:
        session = cast('DeviceSession', bound)
        if session.context.platform != platform:
            raise DeviceSessionError('mobile alias platform does not match the selected device')
        with session.bind():
            return _dispatch_service(row['api'], params)


def android_mobile_action(operation: str, options: Mapping[str, Any],
                          device: Optional[Mapping[str, Any]] = None) -> Any:
    """Run any catalog operation on an explicit Android owner without cross-platform fallback."""
    return _platform_action('android', operation, options, device)


def ios_mobile_action(operation: str, options: Mapping[str, Any],
                      device: Optional[Mapping[str, Any]] = None) -> Any:
    """Run any catalog operation on an explicit iOS owner; never substitute ADB."""
    return _platform_action('ios', operation, options, device)


def run_mobile_actions(session: DeviceSession, actions: list[Any]) -> list[Any]:
    """Validate an entire flat mobile-only batch before input, preserving the selected owner.

    Flow/file/macro/desktop commands are excluded from this panel boundary. Existing
    general executor/matrix interfaces retain their broader scripting contracts.
    """
    # pylint: disable-next=import-outside-toplevel  # reason: executor stays lazy until explicit script execution
    from je_auto_control.utils.executor.action_executor import Executor
    runner = Executor()
    allowed = _mobile_commands(runner.known_commands())
    snapshot = _snapshot_actions(actions, allowed)
    runner.variables.set('device', {'platform': session.context.platform, 'serial': session.context.target,
                                    'url': session.context.target, 'device_id': session.context.device_id})
    _validate_arguments(runner, snapshot)
    results = []
    with session.bind():
        for action in snapshot:
            session.ensure_open()
            # pylint: disable-next=protected-access  # reason: validated native-only dispatch preserves auth/paths/journal, no automatic result logging
            results.append(runner._execute_event(action))
    return results



def _mobile_commands(commands: Iterable[str]) -> set[str]:
    return {name for name in commands if name.startswith(('AC_mobile_', 'AC_android_', 'AC_ios_'))
            and name != 'AC_mobile_run'}


def _valid_action(action: Any, allowed: set[str]) -> bool:
    return isinstance(action, list) and bool(action) and isinstance(action[0], str) and action[0] in allowed


def _snapshot_actions(actions: list[Any], allowed: set[str]) -> list[Any]:
    if not isinstance(actions, list) or not actions:
        raise DeviceSessionError('mobile actions must be a nonempty flat list')
    if any(not _valid_action(action, allowed) for action in actions):
        raise DeviceSessionError('mobile action batch contains a desktop, nested or unknown command')
    snapshot = deepcopy(actions)
    # pylint: disable-next=import-outside-toplevel  # reason: canonical schema validates before all native dispatch
    from je_auto_control.utils.executor.action_schema import validate_actions
    validate_actions(snapshot, allowed)
    return snapshot


def _validate_arguments(runner: Executor, actions: list[Any]) -> None:
    for action in actions:
        # pylint: disable-next=protected-access  # reason: use the canonical variable resolver before all native actions
        params = runner._resolve_runtime_args(action[1], action[0]) if len(action) == 2 else {}
        arguments, keywords = ((), params) if isinstance(params, dict) else (tuple(params), {})
        try:
            signature(runner.event_dict[action[0]]).bind(*arguments, **keywords)
        except TypeError as failure:
            raise DeviceSessionError('mobile batch arguments do not match its service schema') from failure


def mobile_run(actions: list[Any], device: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Execute a mobile-only JSON batch on one owner; summary never echoes device clipboard data."""
    with _owner(device) as session:
        run_mobile_actions(cast('DeviceSession', session), actions)
    return {'completed': len(actions), 'success': True}


__all__ = ['android_mobile_action', 'ios_mobile_action', 'run_mobile_actions', 'mobile_run']
