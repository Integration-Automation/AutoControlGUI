"""Phase 2b — Windows ``WinUSB`` backend (ctypes wiring).

.. warning::
   **ctypes wiring landed; HARDWARE-UNVERIFIED.** This module wraps
   the Win32 ``setupapi.dll`` enumeration calls plus ``winusb.dll``
   ``WinUsb_Initialize`` / ``WinUsb_ControlTransfer`` /
   ``WinUsb_ReadPipe`` / ``WinUsb_WritePipe`` / ``WinUsb_Free``.
   The structural tests cover the import path, the SetupAPI walk
   (which returns an empty list when no WinUSB-bound device is
   present — fine), and the failure path for ``open`` against a VID/PID
   that does not exist.

   **No transfer has been validated against a real device.** Until a
   reviewer signs the relevant rows of
   :doc:`usb_passthrough_security_review`, this backend MUST be
   gated by ``enable_usb_passthrough(True)`` and used only against
   hardware the operator has explicitly approved via the ACL.

The device must already be bound to the WinUSB driver — typically via
Zadig or libwdi. Unbound devices simply don't appear in ``list()``.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import platform
import re
from typing import List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usb.passthrough.backend import (
    BackendDevice, UsbBackend, UsbHandle,
)


# ---------------------------------------------------------------------------
# Win32 constants + structs
# ---------------------------------------------------------------------------


# WinUSB device interface GUID — devices bound to winusb.sys advertise
# themselves under this class. {DEE824EF-729B-4A0E-9C14-B7117D33A817}
_WINUSB_GUID_BYTES = (
    b"\xef\x24\xe8\xde"  # Data1 little-endian
    b"\x9b\x72"          # Data2
    b"\x0e\x4a"          # Data3
    b"\x9c\x14"          # Data4 (8 bytes)
    b"\xb7\x11\x7d\x33\xa8\x17"
)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class _WINUSB_SETUP_PACKET(ctypes.Structure):
    _fields_ = [
        ("RequestType", ctypes.c_ubyte),
        ("Request", ctypes.c_ubyte),
        ("Value", ctypes.c_ushort),
        ("Index", ctypes.c_ushort),
        ("Length", ctypes.c_ushort),
    ]


_DIGCF_PRESENT = 0x00000002
_DIGCF_DEVICEINTERFACE = 0x00000010
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
_ERROR_NO_MORE_ITEMS = 259
_ERROR_INSUFFICIENT_BUFFER = 122
_PIPE_TRANSFER_TIMEOUT = 0x03


_VID_PID_RE = re.compile(
    r"vid_([0-9A-Fa-f]{4})&pid_([0-9A-Fa-f]{4})", re.IGNORECASE,
)


def _winusb_guid() -> _GUID:
    raw = _WINUSB_GUID_BYTES
    guid = _GUID()
    guid.Data1 = int.from_bytes(raw[0:4], "little")
    guid.Data2 = int.from_bytes(raw[4:6], "little")
    guid.Data3 = int.from_bytes(raw[6:8], "little")
    for index in range(8):
        guid.Data4[index] = raw[8 + index]
    return guid


# ---------------------------------------------------------------------------
# Lazy DLL bindings — populated on first WinusbBackend() construction.
# ---------------------------------------------------------------------------


_setupapi: Optional[ctypes.WinDLL] = None
_winusb: Optional[ctypes.WinDLL] = None
_kernel32: Optional[ctypes.WinDLL] = None


def _load_dlls() -> None:
    global _setupapi, _winusb, _kernel32
    if _setupapi is not None:
        return
    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _winusb = ctypes.WinDLL("winusb", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _bind_setupapi(_setupapi)
    _bind_winusb(_winusb)
    _bind_kernel32(_kernel32)


def _bind_setupapi(dll: ctypes.WinDLL) -> None:
    dll.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD,
    ]
    dll.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    dll.SetupDiEnumDeviceInterfaces.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_GUID),
        wintypes.DWORD, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ]
    dll.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    dll.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    dll.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    dll.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    dll.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL


def _bind_winusb(dll: ctypes.WinDLL) -> None:
    dll.WinUsb_Initialize.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE),
    ]
    dll.WinUsb_Initialize.restype = wintypes.BOOL
    dll.WinUsb_Free.argtypes = [wintypes.HANDLE]
    dll.WinUsb_Free.restype = wintypes.BOOL
    dll.WinUsb_ControlTransfer.argtypes = [
        wintypes.HANDLE, _WINUSB_SETUP_PACKET, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    dll.WinUsb_ControlTransfer.restype = wintypes.BOOL
    dll.WinUsb_ReadPipe.argtypes = [
        wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    dll.WinUsb_ReadPipe.restype = wintypes.BOOL
    dll.WinUsb_WritePipe.argtypes = [
        wintypes.HANDLE, ctypes.c_ubyte, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    dll.WinUsb_WritePipe.restype = wintypes.BOOL
    dll.WinUsb_SetPipePolicy.argtypes = [
        wintypes.HANDLE, ctypes.c_ubyte, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p,
    ]
    dll.WinUsb_SetPipePolicy.restype = wintypes.BOOL


def _bind_kernel32(dll: ctypes.WinDLL) -> None:
    dll.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    dll.CreateFileW.restype = wintypes.HANDLE
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class WinusbBackend(UsbBackend):
    """Concrete WinUSB-backed :class:`UsbBackend` (hardware-unverified)."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError(
                "WinusbBackend requires Windows; current platform is "
                f"{platform.system()!r}",
            )
        try:
            _load_dlls()
        except OSError as error:
            raise RuntimeError(
                f"WinUSB DLL load failed: {error!r}",
            ) from error

    def list(self) -> List[BackendDevice]:
        guid = _winusb_guid()
        info_set = _setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid), None, None,
            _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE,
        )
        if info_set is None or info_set == _INVALID_HANDLE_VALUE:
            raise RuntimeError(
                f"SetupDiGetClassDevs failed: {ctypes.get_last_error()}",
            )
        devices: List[BackendDevice] = []
        try:
            index = 0
            iface = _SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)
            while True:
                ok = _setupapi.SetupDiEnumDeviceInterfaces(
                    info_set, None, ctypes.byref(guid), index,
                    ctypes.byref(iface),
                )
                if not ok:
                    error = ctypes.get_last_error()
                    if error == _ERROR_NO_MORE_ITEMS:
                        break
                    autocontrol_logger.warning(
                        "WinUSB enum stopped at %d: error %d", index, error,
                    )
                    break
                index += 1
                path = _resolve_interface_detail(info_set, iface)
                if path is None:
                    continue
                vendor_id, product_id = _parse_vid_pid(path)
                devices.append(BackendDevice(
                    vendor_id=vendor_id or "0000",
                    product_id=product_id or "0000",
                    serial=None,
                    bus_location=path,
                ))
        finally:
            _setupapi.SetupDiDestroyDeviceInfoList(info_set)
        return devices

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> UsbHandle:
        if serial is not None:
            # WinUSB enumeration doesn't include the serial cheaply; fail
            # closed rather than silently ignore the operator's intent.
            autocontrol_logger.info(
                "WinUSB open: serial filter %r ignored "
                "(not yet exposed by enumeration)", serial,
            )
        for device in self.list():
            if device.vendor_id != vendor_id or device.product_id != product_id:
                continue
            return _open_handle(device.bus_location)
        raise RuntimeError(
            f"WinUSB: no device matches {vendor_id}:{product_id}",
        )


# ---------------------------------------------------------------------------
# Handle
# ---------------------------------------------------------------------------


class _WinusbHandle(UsbHandle):
    def __init__(self, file_handle: int, winusb_handle: int) -> None:
        self._file_handle = file_handle
        self._winusb_handle = winusb_handle
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        try:
            _winusb.WinUsb_Free(self._winusb_handle)
        finally:
            try:
                _kernel32.CloseHandle(self._file_handle)
            finally:
                self._closed = True

    def control_transfer(self, *, bm_request_type: int, b_request: int,
                         w_value: int = 0, w_index: int = 0,
                         data: bytes = b"", length: int = 0,
                         timeout_ms: int = 1000) -> bytes:
        self._raise_if_closed()
        is_in = bool(bm_request_type & 0x80)
        if is_in:
            buffer = (ctypes.c_ubyte * int(length))()
            buffer_size = int(length)
        else:
            buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
            buffer_size = len(data)
        setup = _WINUSB_SETUP_PACKET(
            RequestType=bm_request_type & 0xFF,
            Request=b_request & 0xFF,
            Value=w_value & 0xFFFF,
            Index=w_index & 0xFFFF,
            Length=buffer_size & 0xFFFF,
        )
        transferred = wintypes.DWORD(0)
        ok = _winusb.WinUsb_ControlTransfer(
            self._winusb_handle, setup, buffer, buffer_size,
            ctypes.byref(transferred), None,
        )
        if not ok:
            raise RuntimeError(
                f"WinUsb_ControlTransfer failed: {ctypes.get_last_error()}",
            )
        if is_in:
            return bytes(buffer[: transferred.value])
        return b""

    def bulk_transfer(self, *, endpoint: int, direction: str,
                      data: bytes = b"", length: int = 0,
                      timeout_ms: int = 1000) -> bytes:
        return self._endpoint_transfer(
            "bulk", endpoint=endpoint, direction=direction,
            data=data, length=length, timeout_ms=timeout_ms,
        )

    def interrupt_transfer(self, *, endpoint: int, direction: str,
                           data: bytes = b"", length: int = 0,
                           timeout_ms: int = 1000) -> bytes:
        return self._endpoint_transfer(
            "interrupt", endpoint=endpoint, direction=direction,
            data=data, length=length, timeout_ms=timeout_ms,
        )

    def _endpoint_transfer(self, kind: str, *, endpoint: int,
                           direction: str, data: bytes, length: int,
                           timeout_ms: int) -> bytes:
        self._raise_if_closed()
        if direction not in ("in", "out"):
            raise RuntimeError(
                f"unknown direction {direction!r}; want 'in' or 'out'",
            )
        # Apply per-pipe timeout — WinUSB reads/writes don't take a
        # timeout argument directly.
        timeout_value = wintypes.DWORD(int(timeout_ms))
        ok = _winusb.WinUsb_SetPipePolicy(
            self._winusb_handle, endpoint & 0xFF,
            _PIPE_TRANSFER_TIMEOUT, ctypes.sizeof(timeout_value),
            ctypes.byref(timeout_value),
        )
        if not ok:
            autocontrol_logger.debug(
                "WinUsb_SetPipePolicy(timeout) failed: %d",
                ctypes.get_last_error(),
            )
        transferred = wintypes.DWORD(0)
        if direction == "in":
            buffer = (ctypes.c_ubyte * int(length))()
            ok = _winusb.WinUsb_ReadPipe(
                self._winusb_handle, endpoint & 0xFF,
                buffer, int(length), ctypes.byref(transferred), None,
            )
            if not ok:
                raise RuntimeError(
                    f"WinUsb_ReadPipe ({kind}) failed: "
                    f"{ctypes.get_last_error()}",
                )
            return bytes(buffer[: transferred.value])
        out_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        ok = _winusb.WinUsb_WritePipe(
            self._winusb_handle, endpoint & 0xFF,
            out_buffer, len(data), ctypes.byref(transferred), None,
        )
        if not ok:
            raise RuntimeError(
                f"WinUsb_WritePipe ({kind}) failed: "
                f"{ctypes.get_last_error()}",
            )
        return b""

    def _raise_if_closed(self) -> None:
        if self._closed:
            raise RuntimeError("handle is closed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_interface_detail(info_set: int,
                              iface: _SP_DEVICE_INTERFACE_DATA) -> Optional[str]:
    """Two-call pattern: first to size the buffer, second to fill it."""
    needed = wintypes.DWORD(0)
    _setupapi.SetupDiGetDeviceInterfaceDetailW(
        info_set, ctypes.byref(iface), None, 0, ctypes.byref(needed), None,
    )
    if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER:
        return None
    buffer = ctypes.create_string_buffer(needed.value)
    # The struct begins with a DWORD cbSize — value depends on bitness.
    cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
    ctypes.memmove(buffer, ctypes.byref(wintypes.DWORD(cb_size)), 4)
    ok = _setupapi.SetupDiGetDeviceInterfaceDetailW(
        info_set, ctypes.byref(iface),
        buffer, needed.value, None, None,
    )
    if not ok:
        return None
    # Wide string starts after the 4-byte cbSize prefix.
    raw = bytes(buffer.raw[4:])
    text = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
    return text or None


def _parse_vid_pid(path: str) -> tuple:
    """Extract VID/PID from a Windows device interface path."""
    match = _VID_PID_RE.search(path)
    if not match:
        return None, None
    return match.group(1).lower(), match.group(2).lower()


def _open_handle(device_path: str) -> _WinusbHandle:
    file_handle = _kernel32.CreateFileW(
        device_path,
        _GENERIC_READ | _GENERIC_WRITE,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None, _OPEN_EXISTING, _FILE_FLAG_OVERLAPPED, None,
    )
    if file_handle is None or file_handle == _INVALID_HANDLE_VALUE:
        raise RuntimeError(
            f"CreateFileW({device_path!r}) failed: "
            f"{ctypes.get_last_error()}",
        )
    winusb_handle = wintypes.HANDLE()
    ok = _winusb.WinUsb_Initialize(file_handle, ctypes.byref(winusb_handle))
    if not ok:
        last_error = ctypes.get_last_error()
        _kernel32.CloseHandle(file_handle)
        raise RuntimeError(
            f"WinUsb_Initialize failed: {last_error}",
        )
    return _WinusbHandle(file_handle, winusb_handle.value)


__all__ = ["WinusbBackend"]
