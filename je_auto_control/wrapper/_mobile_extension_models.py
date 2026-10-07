"""Passive mobile extension specifications and owner factory contracts."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Protocol

from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError
from je_auto_control.wrapper.capabilities import CapabilityStatus


class MobileExtension(Protocol):
    """One owner-bound adapter; methods must honor context/guard and own cleanup.

    Instances must not be shared between device owners. A configured capability
    describes adapter availability, not successful native platform acceptance.
    """

    context: DeviceContext
    name: str
    version: str
    @property
    def capabilities(self) -> Mapping[str, CapabilityStatus]:
        """Passive capability metadata belonging to this adapter."""

    def install(self, file_path: str) -> None:
        """Install an explicitly selected local application artifact."""

    def files(self, action: str, local_path: str, remote_path: str) -> None:
        """Push/pull files through this platform's supported native transport."""

    def clipboard(self, text: Optional[str] = None) -> Optional[str]:
        """Read or write Unicode without borrowing another platform's shell."""

    def recording(self, file_path: str, duration_s: float) -> None:
        """Record a bounded clip and reclaim owned recorder resources on close."""

    def close(self) -> None:
        """Revoke/clean only this adapter's owned resources; repeated close is safe."""


_OPERATIONS = frozenset(('install', 'files', 'clipboard', 'recording'))


@dataclass(frozen=True)
class MobileExtensionSpec:
    """Passive adapter metadata and a lazy per-owner factory(context, guard).

    The factory must not retain shared native clients. Implementations must use
    context.timeout_s for every native request and honor guard before/after I/O.
    """

    name: str
    version: str
    capabilities: Mapping[str, CapabilityStatus]
    factory: Callable[[DeviceContext, Callable[[], None]], MobileExtension]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not isinstance(self.version, str):
            raise DeviceSessionError('extension name and version must be strings')
        if not self.name or not self.version or not callable(self.factory):
            raise DeviceSessionError('extension requires a name, version and callable owner factory')
        _validate_capabilities(self.capabilities)
        object.__setattr__(self, 'capabilities', MappingProxyType(dict(self.capabilities)))


def _validate_capabilities(capabilities: Mapping[str, CapabilityStatus]) -> None:
    if not isinstance(capabilities, Mapping):
        raise DeviceSessionError('extension capabilities must be a mapping')
    if any(key not in _OPERATIONS or not isinstance(value, CapabilityStatus) or value.desktop_wide
           for key, value in capabilities.items()):
        raise DeviceSessionError('extension capabilities must describe mobile install/files/clipboard/recording')
