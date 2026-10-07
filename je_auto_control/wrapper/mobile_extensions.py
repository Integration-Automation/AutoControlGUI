"""Explicit mobile extension contracts and passive operation capability metadata."""
from __future__ import annotations

from typing import Any, Mapping, TYPE_CHECKING

from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper._mobile_extension_models import MobileExtension, MobileExtensionSpec, _OPERATIONS
from je_auto_control.wrapper.capabilities import CapabilityStatus

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


def extension_capabilities(context: DeviceContext, dependencies: Mapping[str, CapabilityStatus]
                           ) -> dict[str, CapabilityStatus]:
    """Describe native and optional operations without imports, connection or input."""
    primary = dependencies['wda' if context.platform == 'ios' else 'adb']
    result = {operation: CapabilityStatus(primary.state, primary.backend,
                                          'backend dependency only; app/device authorization remains unverified',
                                          primary.recovery, False)
              for operation in ('launch_app', 'stop_app', 'app_state', 'wait_for_app')}
    native = dependencies['wda' if context.platform == 'ios' else 'uiautomator2']
    for operation in ('capture', 'perform', 'type_text'):
        result[operation] = CapabilityStatus(native.state, native.backend,
                                            'SDK dependency only; capture/input permission remains unverified',
                                            native.recovery, False)
    result['device_setup'] = CapabilityStatus('available', 'metadata', 'passive setup; connection is opt-in', '', False)
    result['alert'] = (CapabilityStatus(primary.state, 'wda', 'iOS alert endpoint; permission remains unverified',
                                       primary.recovery, False) if context.platform == 'ios' else
                       CapabilityStatus('unsupported', 'uiautomator2', 'no universal Android alert endpoint',
                                        'Use a specific UI-tree selector.', False))
    for operation in ('install', 'files', 'clipboard', 'recording'):
        result[operation] = _extension_status(context, operation, dependencies)
    return result


def _extension_status(context: DeviceContext, operation: str, dependencies: Mapping[str, CapabilityStatus]
                      ) -> CapabilityStatus:
    if context.platform == 'android' and operation in ('install', 'files'):
        status = dependencies['adb']
        return CapabilityStatus(status.state, 'adb', 'ADB dependency; device access not exercised',
                                status.recovery, False)
    if context.platform == 'android' and operation == 'clipboard':
        status = dependencies['uiautomator2']
        return CapabilityStatus(status.state, 'uiautomator2', 'SDK clipboard; access unverified',
                                status.recovery, False)
    return CapabilityStatus('needs_dependency', 'mobile-extension',
                            'no owned adapter configured for this operation',
                            'Configure a MobileExtension for this device owner.', False)



def run_mobile_extension(session: DeviceSession, operation: str, options: Mapping[str, Any]) -> Any:
    """Execute a supported extension operation through the selected device owner.

    Local files are checked against path policy; an absent optional adapter raises
    needs_dependency. No iOS operation is routed through an Android shell.
    """
    if operation not in _OPERATIONS or not isinstance(options, Mapping):
        raise DeviceSessionError('unknown mobile extension operation or invalid options')
    # pylint: disable-next=import-outside-toplevel  # reason: validation/transport loads only on explicit operation
    from je_auto_control.wrapper._mobile_extension_owner import validated_options
    params = validated_options(operation, options, session.context)
    session.ensure_open()
    status = session.capabilities[operation]
    if status.state in ('needs_dependency', 'unsupported'):
        raise DeviceSessionError(f'{status.state}: {status.reason}; {status.recovery}')
    return session.adapter('extension').execute(operation, params)


__all__ = ['MobileExtension', 'MobileExtensionSpec', 'run_mobile_extension']
