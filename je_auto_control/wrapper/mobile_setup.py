"""Passive SDK setup metadata and explicit read-only native authorization diagnostics."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module, metadata
from typing import Any, Mapping, Optional, TYPE_CHECKING, cast

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper.capabilities import CapabilityStatus
from je_auto_control.wrapper.mobile_actions import _owner

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


@dataclass(frozen=True)
class DeviceSetupReport:
    """Dependency/transport evidence; available HTTP is not native input acceptance."""

    context: DeviceContext
    backend_version: str
    authorization: CapabilityStatus
    endpoint_idle: Optional[bool] = None
    verified_connection: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return JSON evidence, retaining the explicitly selected target and scope."""
        return asdict(self)


def _sdk_version(platform: str) -> str:
    package = 'facebook-wda' if platform == 'ios' else 'uiautomator2'
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return f'{package} not installed; backend version unknown'


def inspect_device_setup(session: DeviceSession, *, connect: bool = False) -> DeviceSetupReport:
    """Inspect dependencies; connect=True performs only bounded GET/status or adb get-state."""
    session.ensure_open()
    if not isinstance(connect, bool):
        raise DeviceSessionError('setup connect flag must be boolean')
    context = session.context
    version = _sdk_version(context.platform)
    dependency = session.capabilities['wda' if context.platform == 'ios' else 'adb']
    if not connect:
        return DeviceSetupReport(context, version, dependency)
    try:
        report = _diagnose_ios(session, version) if context.platform == 'ios' else _diagnose_android(session, version)
    except AutoControlException:
        raise
    except Exception as failure:  # reason: optional transport errors must not imply successful device authorization
        raise DeviceSessionError('mobile setup connection/authorization could not be verified') from failure
    session.ensure_open()
    return report


def _diagnose_android(session: DeviceSession, version: str) -> DeviceSetupReport:
    result = session.adapter('adb').run(['get-state'], check=False)
    if result.returncode != 0 or result.stdout.strip() != b'device' or result.stderr.strip():
        raise DeviceSessionError('Android authorization not confirmed; authorize the selected serial in adb devices')
    status = CapabilityStatus('available', 'adb', 'selected serial reports device; input unverified', '', False)
    return DeviceSetupReport(session.context, version, status, verified_connection=True)


def _diagnose_ios(session: DeviceSession, version: str) -> DeviceSetupReport:
    sdk = import_module('wda')
    # pylint: disable-next=protected-access  # reason: read-only bounded status without SDK retry/session creation
    reply = sdk._unsafe_httpdo(session.context.target.rstrip('/') + '/status', 'GET', None, session.context.timeout_s)
    value = getattr(reply, 'value', None)
    if not isinstance(value, dict) or value.get('ready') is not True:
        raise DeviceSessionError('WDA authorization/readiness not confirmed; check the selected remote endpoint')
    build = value.get('build', {})
    native_version = build.get('version') if isinstance(build, dict) else None
    if isinstance(native_version, str) and native_version:
        version = native_version
    idle = (getattr(reply, 'sessionId') is None) if hasattr(reply, 'sessionId') else None
    status = CapabilityStatus('available', 'wda', 'HTTP ready; app permissions/exclusive ownership remain unverified',
                              'Use a dedicated idle endpoint for app lifecycle.', False)
    return DeviceSetupReport(session.context, version, status, idle, True)


def mobile_setup(device: Optional[Mapping[str, Any]] = None, connect: bool = False) -> dict[str, Any]:
    """JSON setup service shared by facade, AC, MCP, Builder and Mobile Actions."""
    with _owner(device) as session:
        return inspect_device_setup(cast('DeviceSession', session), connect=connect).to_dict()


__all__ = ['DeviceSetupReport', 'inspect_device_setup', 'mobile_setup']
