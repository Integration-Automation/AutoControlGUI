"""Phase 2c — macOS ``IOKit`` backend (structural skeleton).

**This is a skeleton. It will not transfer any bytes.** Wiring the
``IOUSBHostInterface`` callbacks against real USB hardware on macOS is
a discrete project — see the design doc for context.

What's here:

* The :class:`IokitBackend` class.
* Platform / dependency validation (Darwin + pyobjc).
* Documented list of IOKit / pyobjc call sites that still need writing.

What's NOT here:

* ``IOServiceMatching("IOUSBDevice")`` enumeration.
* ``IOUSBHostInterface`` claim + ``CompletionMethod`` callbacks.
* ``CFRunLoop`` thread integration to bridge async IO completions
  back to the WebRTC bridge thread (see design doc OPEN question 6).

Implementation TODOs:

1. Use ``IOKit`` matching dictionary to enumerate USB devices by
   vendor / product. Translate IOKit error codes into ``RuntimeError``.
2. Open the device interface (``IOUSBHostInterface`` on 10.12+).
3. Wrap synchronous control / bulk / interrupt calls; for async
   transfers, register completion callbacks tied to a dedicated
   ``CFRunLoop`` thread.
4. Handle ``kIOReturnExclusiveAccess`` (another driver claimed the
   device) with a clear "cannot claim, busy" RuntimeError.
5. Document the entitlement / notarisation story for distribution.
6. Hardware test matrix similar to WinUSB: bulk, HID, composite.
"""
from __future__ import annotations

import platform
from typing import List, Optional

from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, UsbBackend, UsbHandle,
)


class IokitBackend(UsbBackend):
    """Skeleton — see module docstring for the implementation TODO list."""

    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError(
                "IokitBackend requires macOS; current platform is "
                f"{platform.system()!r}",
            )
        try:
            import objc  # noqa: F401  # pyobjc-core
        except ImportError as error:
            raise RuntimeError(
                "IokitBackend requires pyobjc; run 'pip install pyobjc' "
                "to enable the IOKit passthrough backend",
            ) from error

    def list(self) -> List[BackendDevice]:
        raise NotImplementedError(
            "IOKit enumeration not implemented yet — see "
            "iokit_backend module docstring for the TODO list",
        )

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> UsbHandle:
        raise NotImplementedError(
            "IOKit open not implemented yet — see "
            "iokit_backend module docstring for the TODO list",
        )


__all__ = ["IokitBackend"]
