"""Frozen mobile identities, validated endpoints and typed ownership failures."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Literal, Mapping, Optional
from urllib.parse import SplitResult, urlsplit

from je_auto_control.utils.exception.exceptions import AutoControlException


class DeviceSessionError(AutoControlException):
    """Invalid, closed or mismatched mobile ownership; never retry another device."""

    state = 'unsupported'


@dataclass(frozen=True)
class DeviceContext:
    """Explicit mobile identity/config; timeout bounds each native request.

    Android target defaults to device_id (an ADB serial), while iOS requires an
    explicit WDA target URL. No SDK, input, scan or network connection is made.
    """

    platform: Literal['android', 'ios']
    device_id: str
    target: str = field(default='', repr=False)
    timeout_s: float = 10.0
    adb_path: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.platform not in ('android', 'ios'):
            raise DeviceSessionError('device platform must be android or ios')
        _required_text(self.device_id, 'device_id')
        if self.timeout_s is None:
            raise DeviceSessionError('device timeout must be finite and positive')
        timeout = bounded_timeout(300, self.timeout_s)
        if float(self.timeout_s) > 300:
            raise DeviceSessionError('device timeout must be at most 300 seconds')
        object.__setattr__(self, 'timeout_s', timeout)
        object.__setattr__(self, 'target', _configured_target(self.platform, self.device_id, self.target))
        if self.adb_path is not None:
            _required_text(self.adb_path, 'adb_path')

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any], *, index: int = 0) -> DeviceContext:
        """Freeze a legacy matrix spec without changing that spec or the defaults."""
        if not isinstance(spec, Mapping):
            raise DeviceSessionError('device specs must be objects')
        platform = spec.get('platform', '')
        target = spec.get('serial' if platform == 'android' else 'url', spec.get('target', ''))
        identity = spec.get('device_id') or target or f'device-{index}'
        return cls(platform, identity, target=target, timeout_s=spec.get('timeout_s', 10),
                   adb_path=spec.get('adb_path'))


def bounded_timeout(limit: float, requested: Optional[float]) -> float:
    """Validate and clamp one request without changing any SDK global timeout."""
    value = limit if requested is None else requested
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise DeviceSessionError('device timeout must be finite and positive')
    return min(limit, float(value))


def _required_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise DeviceSessionError(f'{name} must be nonempty text without NUL')


def _configured_target(platform: str, identity: str, value: str) -> str:
    if not isinstance(value, str):
        raise DeviceSessionError('device target must be text')
    target = value or (identity if platform == 'android' else '')
    _required_text(target, 'device target')
    if platform == 'ios':
        _validate_wda_url(target)
    return target


def _validate_wda_url(target: str) -> None:
    try:
        parsed = urlsplit(target)
        port = parsed.port
    except ValueError as failure:
        raise DeviceSessionError('invalid WDA endpoint') from failure
    if parsed.scheme not in ('http', 'https', 'http+usbmux') or not parsed.hostname or port == 0:
        raise DeviceSessionError('WDA target must be an explicit HTTP/HTTPS/usbmux endpoint')
    _reject_url_credentials(target, parsed)


def _reject_url_credentials(target: str, parsed: SplitResult) -> None:
    if (parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment
            or any(character.isspace() for character in target)):
        raise DeviceSessionError('WDA target must be an explicit HTTP/HTTPS/usbmux endpoint without URL credentials')
