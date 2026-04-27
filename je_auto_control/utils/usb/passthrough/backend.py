"""Backend ABCs for USB passthrough + a libusb-backed implementation.

Phase 2a.1 wires the three transfer methods (``control_transfer``,
``bulk_transfer``, ``interrupt_transfer``) for both backends. The
:class:`FakeUsbBackend` exposes an injectable ``transfer_hook`` so tests
can return arbitrary bytes or raise.
"""
from __future__ import annotations

import abc
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


@dataclass
class BackendDevice:
    """One device the backend is willing to expose to the passthrough layer."""

    vendor_id: str
    product_id: str
    serial: Optional[str] = None
    bus_location: Optional[str] = None


class UsbBackend(abc.ABC):
    """Per-OS USB driver wrapper."""

    @abc.abstractmethod
    def list(self) -> List[BackendDevice]:
        """Enumerate devices this backend can claim."""

    @abc.abstractmethod
    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> "UsbHandle":
        """Acquire an exclusive handle on the matching device.

        Implementations raise ``RuntimeError`` (or a subclass) if the
        device is unavailable, already claimed, or the user lacks
        permission.
        """


class UsbHandle(abc.ABC):
    """Open handle on a single USB device."""

    @abc.abstractmethod
    def close(self) -> None:
        """Release the device. Idempotent."""

    @abc.abstractmethod
    def control_transfer(
        self,
        *,
        bm_request_type: int,
        b_request: int,
        w_value: int = 0,
        w_index: int = 0,
        data: bytes = b"",
        length: int = 0,
        timeout_ms: int = 1000,
    ) -> bytes:
        """USB control transfer. ``data`` for OUT, ``length`` for IN."""

    @abc.abstractmethod
    def bulk_transfer(
        self,
        *,
        endpoint: int,
        direction: str,           # "in" or "out"
        data: bytes = b"",
        length: int = 0,
        timeout_ms: int = 1000,
    ) -> bytes:
        """Bulk endpoint transfer. ``data`` for OUT, ``length`` for IN."""

    @abc.abstractmethod
    def interrupt_transfer(
        self,
        *,
        endpoint: int,
        direction: str,           # "in" or "out"
        data: bytes = b"",
        length: int = 0,
        timeout_ms: int = 1000,
    ) -> bytes:
        """Interrupt endpoint transfer. ``data`` for OUT, ``length`` for IN."""


# ---------------------------------------------------------------------------
# Libusb (pyusb) backend
# ---------------------------------------------------------------------------


class LibusbBackend(UsbBackend):
    """Concrete backend over ``pyusb`` (libusb-1.0).

    ``pyusb`` is optional; if it's not installed the constructor raises
    ``RuntimeError`` and the caller is expected to fall back / disable
    passthrough.
    """

    def __init__(self) -> None:
        try:
            import usb.core  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "pyusb not installed; run 'pip install pyusb' to enable "
                "the libusb passthrough backend",
            ) from error
        self._usb_core = usb.core

    def list(self) -> List[BackendDevice]:
        devices = list(self._usb_core.find(find_all=True))
        return [
            BackendDevice(
                vendor_id=f"{int(getattr(d, 'idVendor', 0)):04x}",
                product_id=f"{int(getattr(d, 'idProduct', 0)):04x}",
                serial=_safe_string(d, "serial_number"),
                bus_location=_pyusb_bus(d),
            )
            for d in devices
        ]

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> "UsbHandle":
        vid_int = int(vendor_id, 16)
        pid_int = int(product_id, 16)
        match = self._usb_core.find(
            find_all=False, idVendor=vid_int, idProduct=pid_int,
        )
        if match is None:
            raise RuntimeError(
                f"no USB device matches {vendor_id}:{product_id}",
            )
        if serial is not None:
            actual = _safe_string(match, "serial_number")
            if actual != serial:
                raise RuntimeError(
                    f"serial mismatch: requested {serial!r}, found {actual!r}",
                )
        return _LibusbHandle(match)


class _LibusbHandle(UsbHandle):
    def __init__(self, device: Any) -> None:
        self._device = device
        self._closed = False
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._device.reset()
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: best-effort cleanup; surface via logger so it's not invisible
                autocontrol_logger.debug(
                    "libusb close: device.reset() raised %r", error,
                )
            self._closed = True

    def control_transfer(self, *, bm_request_type: int, b_request: int,
                         w_value: int = 0, w_index: int = 0,
                         data: bytes = b"", length: int = 0,
                         timeout_ms: int = 1000) -> bytes:
        self._raise_if_closed()
        # pyusb's ctrl_transfer: data_or_wLength is bytes for OUT,
        # an int (length) for IN. Direction is encoded in bm_request_type
        # bit 7 (0x80 = device-to-host).
        is_in = bool(bm_request_type & 0x80)
        payload: Any = int(length) if is_in else bytes(data)
        try:
            result = self._device.ctrl_transfer(
                int(bm_request_type), int(b_request),
                int(w_value), int(w_index), payload, int(timeout_ms),
            )
        except Exception as error:
            raise RuntimeError(f"control_transfer: {error}") from error
        if is_in:
            return bytes(result)
        # For OUT transfers pyusb returns the byte count actually written.
        # Echo nothing — the wire response just signals success.
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
        if direction == "in":
            try:
                result = self._device.read(
                    int(endpoint), int(length), int(timeout_ms),
                )
            except Exception as error:
                raise RuntimeError(f"{kind} read: {error}") from error
            return bytes(result)
        if direction == "out":
            try:
                self._device.write(
                    int(endpoint), bytes(data), int(timeout_ms),
                )
            except Exception as error:
                raise RuntimeError(f"{kind} write: {error}") from error
            return b""
        raise RuntimeError(f"unknown direction {direction!r}; want 'in' or 'out'")

    def _raise_if_closed(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("handle is closed")


def _safe_string(dev: Any, attr: str) -> Optional[str]:
    try:
        text = getattr(dev, attr, None)
    except (OSError, ValueError, NotImplementedError):
        return None
    if text is None:
        return None
    return str(text).strip() or None


def _pyusb_bus(dev: Any) -> Optional[str]:
    bus = getattr(dev, "bus", None)
    address = getattr(dev, "address", None)
    if bus is None and address is None:
        return None
    return f"bus={bus} addr={address}"


# ---------------------------------------------------------------------------
# Fake backend (tests + dry-run)
# ---------------------------------------------------------------------------


class FakeUsbBackend(UsbBackend):
    """Deterministic in-memory backend for tests.

    Constructor takes a list of :class:`BackendDevice` to expose plus
    optional callables to override ``open`` behaviour per (vid, pid).
    """

    def __init__(
        self,
        devices: Optional[List[BackendDevice]] = None,
        *,
        open_hook: Optional[Callable[[str, str, Optional[str]], "UsbHandle"]] = None,
    ) -> None:
        self._devices = list(devices or [])
        self._open_hook = open_hook
        self._open_handles: Dict[int, "FakeUsbHandle"] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def list(self) -> List[BackendDevice]:
        return list(self._devices)

    def open(self, *, vendor_id: str, product_id: str,
             serial: Optional[str] = None) -> "UsbHandle":
        if self._open_hook is not None:
            return self._open_hook(vendor_id, product_id, serial)
        for dev in self._devices:
            if dev.vendor_id != vendor_id or dev.product_id != product_id:
                continue
            if serial is not None and dev.serial != serial:
                continue
            with self._lock:
                handle_id = self._next_id
                self._next_id += 1
                handle = FakeUsbHandle(self, handle_id, dev)
                self._open_handles[handle_id] = handle
            return handle
        raise RuntimeError(
            f"no fake device matches {vendor_id}:{product_id}",
        )

    @property
    def open_handle_count(self) -> int:
        with self._lock:
            return len(self._open_handles)

    def _on_handle_closed(self, handle_id: int) -> None:
        with self._lock:
            self._open_handles.pop(handle_id, None)


class FakeUsbHandle(UsbHandle):
    """Test handle. Transfer methods echo / return canned bytes.

    Override behaviour by setting ``transfer_hook`` to a callable
    ``(kind, kwargs) -> bytes``; raising from the hook simulates a
    backend error.
    """

    def __init__(self, backend: FakeUsbBackend, handle_id: int,
                 device: BackendDevice,
                 transfer_hook: Optional[Callable[[str, Dict[str, Any]], bytes]] = None,
                 ) -> None:
        self._backend = backend
        self._handle_id = handle_id
        self._device = device
        self._closed = False
        self._lock = threading.Lock()
        self.transfer_hook = transfer_hook
        self.calls: List[Dict[str, Any]] = []

    @property
    def device(self) -> BackendDevice:
        return self._device

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._backend._on_handle_closed(self._handle_id)

    def control_transfer(self, *, bm_request_type: int, b_request: int,
                         w_value: int = 0, w_index: int = 0,
                         data: bytes = b"", length: int = 0,
                         timeout_ms: int = 1000) -> bytes:
        return self._dispatch("control", {
            "bm_request_type": bm_request_type, "b_request": b_request,
            "w_value": w_value, "w_index": w_index,
            "data": bytes(data), "length": int(length),
            "timeout_ms": int(timeout_ms),
        })

    def bulk_transfer(self, *, endpoint: int, direction: str,
                      data: bytes = b"", length: int = 0,
                      timeout_ms: int = 1000) -> bytes:
        return self._dispatch("bulk", {
            "endpoint": int(endpoint), "direction": direction,
            "data": bytes(data), "length": int(length),
            "timeout_ms": int(timeout_ms),
        })

    def interrupt_transfer(self, *, endpoint: int, direction: str,
                           data: bytes = b"", length: int = 0,
                           timeout_ms: int = 1000) -> bytes:
        return self._dispatch("interrupt", {
            "endpoint": int(endpoint), "direction": direction,
            "data": bytes(data), "length": int(length),
            "timeout_ms": int(timeout_ms),
        })

    def _dispatch(self, kind: str, kwargs: Dict[str, Any]) -> bytes:
        with self._lock:
            if self._closed:
                raise RuntimeError("handle is closed")
        self.calls.append({"kind": kind, **kwargs})
        if self.transfer_hook is not None:
            return self.transfer_hook(kind, kwargs)
        # Default behaviour: echo OUT data (return empty) or fabricate
        # ``length`` zero bytes for IN.
        if kwargs.get("direction") == "out" or kwargs.get("data"):
            return b""
        return b"\x00" * int(kwargs.get("length", 0))


__all__ = [
    "BackendDevice", "FakeUsbBackend", "FakeUsbHandle",
    "LibusbBackend", "UsbBackend", "UsbHandle",
]
