"""Explicit-session ADB client, without the executor's process-wide cache."""
from __future__ import annotations

import subprocess  # nosec B404  # reason: return annotation for the existing argv-only ADB transport
from typing import Callable, Optional, Sequence

from je_auto_control.android.adb_client import AdbClient
from je_auto_control.wrapper._mobile_models import DeviceContext, DeviceSessionError, bounded_timeout


class OwnedAdbClient(AdbClient):
    """Guard requests and late results; preserve the existing bounded ADB transport."""

    def __init__(self, context: DeviceContext, guard: Callable[[], None]) -> None:
        self._context = context
        self._guard = guard
        super().__init__(adb_path=context.adb_path, default_serial=context.target, timeout_s=context.timeout_s)

    def run(self, args: Sequence[str], *, serial: Optional[str] = None,
            input_bytes: Optional[bytes] = None, timeout: Optional[float] = None,
            check: bool = True) -> subprocess.CompletedProcess[bytes]:
        """Reject cross-device overrides and successful completion after cancellation."""
        self._guard()
        if serial is not None and serial != self._context.target:
            raise DeviceSessionError('explicit serial does not match the active device context')
        result = super().run(args, serial=self._context.target, input_bytes=input_bytes,
                             timeout=bounded_timeout(self._context.timeout_s, timeout), check=check)
        self._guard()
        return result
