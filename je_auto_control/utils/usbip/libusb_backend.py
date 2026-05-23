"""Phase 9.6: production URB backend on top of PyUSB / libusb.

The Phase 8.2 :class:`UrbBackend` abstract gives the USB/IP server a
pluggable URB executor. This module ships the production implementation:
real device enumeration via PyUSB, real URB forwarding through
``libusb_submit_transfer`` (control + bulk + interrupt — isochronous
deferred to a future phase since vhci-hcd / usbip-win clients
synthesise iso scheduling locally anyway).

PyUSB is an optional dep — the backend's constructor probes the
import and degrades to ``available=False`` instead of raising at
module load time, so a host without libusb installed still imports
the parent ``usbip`` package cleanly.

USB endpoint addressing follows the kernel convention used by the
USB/IP protocol: ``ep`` is the *endpoint number* (0-15) and
``direction`` is 0 for OUT or 1 for IN. The wire-level "endpoint
address" byte that libusb wants is ``ep | (direction << 7)``.
"""
from __future__ import annotations

from typing import List

from je_auto_control.utils.usbip.backend import (
    UrbBackend, UrbRequest, UrbResponse,
)
from je_auto_control.utils.usbip.protocol import (
    UsbIpDevice, UsbIpInterface,
)


_USB_TIMEOUT_MS = 5_000  # 5 s ceiling per URB; matches kernel default.


def _try_pyusb():
    try:
        import usb.core  # noqa: F401
        import usb.util  # noqa: F401
        return True
    except ImportError:
        return False


def _direction_in(direction: int) -> bool:
    return bool(direction)


def _endpoint_address(direction: int, ep: int) -> int:
    """Combine the USB/IP ``ep`` + ``direction`` fields into a libusb byte."""
    return (int(ep) & 0x7F) | (0x80 if _direction_in(direction) else 0x00)


def _is_control_endpoint(ep: int) -> bool:
    return int(ep) == 0


class LibUsbBackend(UrbBackend):
    """URB backend that pairs the USB/IP server with the local libusb.

    The backend keeps a small map of ``devid → pyusb Device``. ``devid``
    follows the USB/IP convention: ``(busnum << 16) | devnum``, so the
    same id round-trips between OP_REP_IMPORT and CMD_SUBMIT.
    """

    def __init__(self) -> None:
        self._available = _try_pyusb()
        self._device_cache: dict = {}

    @property
    def available(self) -> bool:
        return self._available

    def list_devices(self) -> List[UsbIpDevice]:
        if not self._available:
            return []
        import usb.core
        import usb.util
        out: List[UsbIpDevice] = []
        for dev in usb.core.find(find_all=True):
            try:
                manufacturer = usb.util.get_string(dev, dev.iManufacturer) or ""
            except (usb.core.USBError, ValueError):
                manufacturer = ""
            try:
                cfg = dev.get_active_configuration()
                interfaces = [
                    UsbIpInterface(
                        bInterfaceClass=int(intf.bInterfaceClass),
                        bInterfaceSubClass=int(intf.bInterfaceSubClass),
                        bInterfaceProtocol=int(intf.bInterfaceProtocol),
                    )
                    for intf in cfg
                ]
                num_interfaces = int(cfg.bNumInterfaces)
                cfg_value = int(cfg.bConfigurationValue)
            except (usb.core.USBError, NotImplementedError):
                interfaces = []
                num_interfaces = 0
                cfg_value = 0
            busid = f"{dev.bus}-{dev.address}"
            devid = (int(dev.bus) << 16) | int(dev.address)
            self._device_cache[devid] = dev
            out.append(UsbIpDevice(
                path=f"/sys/devices/usb/{busid}",
                busid=busid,
                busnum=int(dev.bus),
                devnum=int(dev.address),
                speed=int(getattr(dev, "speed", 0) or 0),
                vendor_id=int(dev.idVendor),
                product_id=int(dev.idProduct),
                bcd_device=int(getattr(dev, "bcdDevice", 0)),
                device_class=int(dev.bDeviceClass),
                device_subclass=int(dev.bDeviceSubClass),
                device_protocol=int(dev.bDeviceProtocol),
                configuration_value=cfg_value,
                num_configurations=int(getattr(dev, "bNumConfigurations", 1)),
                num_interfaces=num_interfaces,
                interfaces=interfaces,
            ))
            del manufacturer  # placeholder for future iManufacturer plumbing
        return out

    def submit_urb(self, request: UrbRequest) -> UrbResponse:
        if not self._available:
            return UrbResponse(status=-19, actual_length=0)  # -ENODEV
        device = self._device_cache.get(request.devid)
        if device is None:
            return UrbResponse(status=-19, actual_length=0)
        try:
            if _is_control_endpoint(request.ep):
                return self._submit_control(device, request)
            return self._submit_bulk_or_interrupt(device, request)
        except Exception as error:  # noqa: BLE001 — translate to URB status
            return UrbResponse(
                status=_translate_error(error),
                actual_length=0,
            )

    # --- per-endpoint-type helpers --------------------------------------

    @staticmethod
    def _submit_control(device, request: UrbRequest) -> UrbResponse:
        """Control transfer (ep 0). Setup packet lives in ``request.setup``."""
        if len(request.setup) != 8:
            return UrbResponse(status=-22, actual_length=0)  # -EINVAL
        bmRequestType = request.setup[0]
        bRequest = request.setup[1]
        wValue = int.from_bytes(request.setup[2:4], "little")
        wIndex = int.from_bytes(request.setup[4:6], "little")
        wLength = int.from_bytes(request.setup[6:8], "little")
        if _direction_in(request.direction):
            data = device.ctrl_transfer(
                bmRequestType, bRequest, wValue, wIndex,
                wLength, timeout=_USB_TIMEOUT_MS,
            )
            payload = bytes(data)
            return UrbResponse(
                status=0, actual_length=len(payload), data=payload,
            )
        sent = device.ctrl_transfer(
            bmRequestType, bRequest, wValue, wIndex,
            request.transfer_buffer, timeout=_USB_TIMEOUT_MS,
        )
        return UrbResponse(status=0, actual_length=int(sent or 0))

    @staticmethod
    def _submit_bulk_or_interrupt(device, request: UrbRequest) -> UrbResponse:
        """Bulk / interrupt transfer through ``Device.read`` or ``Device.write``."""
        endpoint = _endpoint_address(request.direction, request.ep)
        if _direction_in(request.direction):
            buf = device.read(
                endpoint, request.transfer_buffer_length,
                timeout=_USB_TIMEOUT_MS,
            )
            payload = bytes(buf)
            return UrbResponse(
                status=0, actual_length=len(payload), data=payload,
            )
        written = device.write(
            endpoint, request.transfer_buffer,
            timeout=_USB_TIMEOUT_MS,
        )
        return UrbResponse(status=0, actual_length=int(written or 0))


def _translate_error(error: BaseException) -> int:
    """Map a PyUSB / OSError to a kernel-style negative errno.

    Detailed mapping (-110 = -ETIMEDOUT, -22 = -EINVAL, -71 = -EPROTO)
    matters because the kernel's vhci-hcd surfaces the same codes to
    userspace; an inaccurate translation makes USB stacks misbehave.
    """
    name = type(error).__name__
    if name == "USBTimeoutError":
        return -110
    if name == "USBError":
        # Take errno from the OS where available; else fall back to -EIO.
        return -getattr(error, "errno", 5) or -5
    if isinstance(error, ValueError):
        return -22
    return -71


__all__ = ["LibUsbBackend"]
