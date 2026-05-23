"""Pluggable URB execution backend for the USB/IP server."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from je_auto_control.utils.usbip.protocol import UsbIpDevice


@dataclass
class UrbRequest:
    """One URB the client wants the host to submit to the real device."""
    seqnum: int
    devid: int
    direction: int
    ep: int
    setup: bytes
    transfer_buffer: bytes
    transfer_buffer_length: int


@dataclass
class UrbResponse:
    """Result of executing a URB on the real device."""
    status: int           # 0 = success; negative errno otherwise
    actual_length: int
    data: bytes = b""


class UrbBackend:
    """Abstract URB execution. Subclass for libusb / WinUSB / FakeUrbBackend.

    The two methods exporters must implement are :meth:`list_devices`
    (used by OP_REQ_DEVLIST) and :meth:`submit_urb` (USBIP_CMD_SUBMIT).
    ``find_by_busid`` is given a default implementation built on top
    of ``list_devices``.
    """

    def list_devices(self) -> List[UsbIpDevice]:
        raise NotImplementedError

    def find_by_busid(self, busid: str) -> Optional[UsbIpDevice]:
        for dev in self.list_devices():
            if dev.busid == busid:
                return dev
        return None

    def submit_urb(self, request: UrbRequest) -> UrbResponse:
        raise NotImplementedError


class FakeUrbBackend(UrbBackend):
    """In-memory scriptable backend — what the tests + dev demos use.

    Devices are seeded in the constructor; URBs are answered from a
    dict keyed by ``(devid, direction, ep)``. Unanswered URBs return
    a "no such device" error so consumers can detect drift.
    """

    def __init__(self, devices: Optional[List[UsbIpDevice]] = None) -> None:
        self._devices = list(devices or [])
        self._urb_responses: Dict[tuple, List[UrbResponse]] = {}
        self.received: List[UrbRequest] = []

    def add_device(self, device: UsbIpDevice) -> None:
        self._devices.append(device)

    def script_urb(self, *, devid: int, direction: int, ep: int,
                   response: UrbResponse) -> None:
        """Queue a response for the next matching URB."""
        self._urb_responses.setdefault(
            (devid, direction, ep), [],
        ).append(response)

    def list_devices(self) -> List[UsbIpDevice]:
        return list(self._devices)

    def submit_urb(self, request: UrbRequest) -> UrbResponse:
        self.received.append(request)
        key = (request.devid, request.direction, request.ep)
        queue = self._urb_responses.get(key)
        if not queue:
            return UrbResponse(status=-19, actual_length=0)  # -ENODEV
        return queue.pop(0)


__all__ = ["UrbBackend", "FakeUrbBackend", "UrbRequest", "UrbResponse"]
