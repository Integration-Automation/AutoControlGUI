"""Phase 2c — macOS ``IOKit`` backend.

Enumeration is native: it walks the IOKit registry through ``ctypes``
bindings to ``IOKit.framework`` / ``CoreFoundation.framework`` (no
``pyobjc`` dependency) and reads each USB device's ``idVendor`` /
``idProduct`` / serial / ``locationID``.

Transfers (open question 6) go through ``libusb`` via
:class:`LibusbBackend`. ``libusb`` is the hardware-proven USB path on
macOS, and reusing it avoids hand-rolling the COM-style
``IOUSBHostInterface`` plugin vtable in ``ctypes`` — code that could not
be verified without hardware and would duplicate logic libusb already
ships. The native IOKit enumeration still lets the host list devices
without pyusb installed; an actual *claim* requires libusb.

.. warning::
   **HARDWARE-UNVERIFIED.** The ctypes enumeration bindings are
   structurally tested but have not been validated against real macOS
   USB hardware. Until a reviewer signs the relevant rows of
   :doc:`usb_passthrough_security_review`, this backend MUST be gated by
   ``enable_usb_passthrough(True)`` and used only against hardware the
   operator has approved via the ACL.

Distribution note (open question 6): a directly distributed (non App
Store) build must be notarised; libusb device access on macOS needs no
special entitlement, but System Integrity Protection still hides Apple
internal devices and some USB-C peripherals. See the operator guide.
"""
from __future__ import annotations

import ctypes
import platform
from typing import List, Optional

from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, LibusbBackend, UsbBackend, UsbHandle,
)


_K_CFSTRING_UTF8 = 0x08000100
_K_CFNUMBER_SINT64 = 4
_K_IO_MAIN_PORT_DEFAULT = 0
_IOKIT_PATH = "/System/Library/Frameworks/IOKit.framework/IOKit"
_CF_PATH = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_STRING_BUFFER_BYTES = 512


def _load_frameworks():
    """Load + bind IOKit and CoreFoundation; raise RuntimeError on failure."""
    try:
        iokit = ctypes.cdll.LoadLibrary(_IOKIT_PATH)
        core = ctypes.cdll.LoadLibrary(_CF_PATH)
    except OSError as error:
        raise RuntimeError(
            f"failed to load macOS IOKit/CoreFoundation: {error!r}",
        ) from error
    _bind_core_foundation(core)
    _bind_iokit(iokit)
    return iokit, core


def _bind_core_foundation(core: ctypes.CDLL) -> None:
    core.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32,
    ]
    core.CFStringCreateWithCString.restype = ctypes.c_void_p
    core.CFStringGetCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32,
    ]
    core.CFStringGetCString.restype = ctypes.c_bool
    core.CFNumberGetValue.argtypes = [
        ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p,
    ]
    core.CFNumberGetValue.restype = ctypes.c_bool
    core.CFRelease.argtypes = [ctypes.c_void_p]
    core.CFRelease.restype = None


def _bind_iokit(iokit: ctypes.CDLL) -> None:
    iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]
    iokit.IOServiceMatching.restype = ctypes.c_void_p
    iokit.IOServiceGetMatchingServices.argtypes = [
        ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
    ]
    iokit.IOServiceGetMatchingServices.restype = ctypes.c_int
    iokit.IOIteratorNext.argtypes = [ctypes.c_uint32]
    iokit.IOIteratorNext.restype = ctypes.c_uint32
    iokit.IORegistryEntryCreateCFProperty.argtypes = [
        ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
    ]
    iokit.IORegistryEntryCreateCFProperty.restype = ctypes.c_void_p
    iokit.IOObjectRelease.argtypes = [ctypes.c_uint32]
    iokit.IOObjectRelease.restype = ctypes.c_int


class IokitBackend(UsbBackend):
    """Native IOKit enumeration; libusb-backed transfers (see module doc)."""

    def __init__(self) -> None:
        if platform.system() != "Darwin":
            raise RuntimeError(
                "IokitBackend requires macOS; current platform is "
                f"{platform.system()!r}",
            )
        self._iokit, self._core = _load_frameworks()
        self._transfer_backend: Optional[LibusbBackend] = None

    def list(self) -> List[BackendDevice]:
        return _enumerate(self._iokit, self._core)

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> UsbHandle:
        if self._transfer_backend is None:
            try:
                self._transfer_backend = LibusbBackend()
            except RuntimeError as error:
                raise RuntimeError(
                    "IOKit enumeration works without libusb, but claiming a "
                    "device for transfers needs it: " + str(error),
                ) from error
        return self._transfer_backend.open(
            vendor_id=vendor_id, product_id=product_id, serial=serial,
        )


# ---------------------------------------------------------------------------
# Enumeration helpers
# ---------------------------------------------------------------------------


def _enumerate(iokit: ctypes.CDLL, core: ctypes.CDLL) -> List[BackendDevice]:
    matching = iokit.IOServiceMatching(b"IOUSBDevice")
    if not matching:
        matching = iokit.IOServiceMatching(b"IOUSBHostDevice")
    if not matching:
        raise RuntimeError("IOServiceMatching returned NULL for USB devices")
    iterator = ctypes.c_uint32(0)
    result = iokit.IOServiceGetMatchingServices(
        _K_IO_MAIN_PORT_DEFAULT, matching, ctypes.byref(iterator),
    )
    if result != 0:
        raise RuntimeError(
            f"IOServiceGetMatchingServices failed: kern_return={result}",
        )
    devices: List[BackendDevice] = []
    try:
        while True:
            service = iokit.IOIteratorNext(iterator)
            if not service:
                break
            try:
                device = _read_device(iokit, core, service)
            finally:
                iokit.IOObjectRelease(service)
            if device is not None:
                devices.append(device)
    finally:
        iokit.IOObjectRelease(iterator)
    return devices


def _read_device(iokit: ctypes.CDLL, core: ctypes.CDLL,
                 service: int) -> Optional[BackendDevice]:
    vendor = _read_number(iokit, core, service, "idVendor")
    product = _read_number(iokit, core, service, "idProduct")
    if vendor is None or product is None:
        return None
    location = _read_number(iokit, core, service, "locationID")
    return BackendDevice(
        vendor_id=f"{vendor & 0xFFFF:04x}",
        product_id=f"{product & 0xFFFF:04x}",
        serial=_read_string(iokit, core, service, "USB Serial Number"),
        bus_location=(None if location is None else f"0x{location & 0xFFFFFFFF:08x}"),
    )


def _property_ref(iokit: ctypes.CDLL, core: ctypes.CDLL,
                  service: int, key_name: str):
    key = core.CFStringCreateWithCString(
        None, key_name.encode("utf-8"), _K_CFSTRING_UTF8,
    )
    if not key:
        return None
    try:
        return iokit.IORegistryEntryCreateCFProperty(service, key, None, 0)
    finally:
        core.CFRelease(key)


def _read_number(iokit: ctypes.CDLL, core: ctypes.CDLL,
                 service: int, key_name: str) -> Optional[int]:
    ref = _property_ref(iokit, core, service, key_name)
    if not ref:
        return None
    try:
        out = ctypes.c_int64(0)
        ok = core.CFNumberGetValue(ref, _K_CFNUMBER_SINT64, ctypes.byref(out))
        return int(out.value) if ok else None
    finally:
        core.CFRelease(ref)


def _read_string(iokit: ctypes.CDLL, core: ctypes.CDLL,
                 service: int, key_name: str) -> Optional[str]:
    ref = _property_ref(iokit, core, service, key_name)
    if not ref:
        return None
    try:
        buffer = ctypes.create_string_buffer(_STRING_BUFFER_BYTES)
        ok = core.CFStringGetCString(
            ref, buffer, len(buffer), _K_CFSTRING_UTF8,
        )
        if not ok:
            return None
        text = buffer.value.decode("utf-8", errors="replace").strip()
        return text or None
    finally:
        core.CFRelease(ref)


__all__ = ["IokitBackend"]
