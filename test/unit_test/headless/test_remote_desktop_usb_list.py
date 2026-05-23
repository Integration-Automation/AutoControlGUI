"""Phase 6.9 (subset): remote USB-device-list RPC tests."""
from io import BytesIO
from unittest.mock import patch

import pytest

from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
from je_auto_control.utils.remote_desktop.viewer import RemoteDesktopViewer
from je_auto_control.utils.usb import UsbDevice, UsbEnumerationResult


def _jpeg() -> bytes:
    from PIL import Image
    img = Image.new("RGB", (16, 16), color=(0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def _fake_enum(devices: list) -> UsbEnumerationResult:
    return UsbEnumerationResult(
        backend="fake", devices=devices, error=None,
    )


def test_viewer_can_list_remote_usb_devices():
    fake_devices = [
        UsbDevice(vendor_id="046d", product_id="c52b",
                  manufacturer="Logitech", product="USB Receiver",
                  serial="ABC123"),
        UsbDevice(vendor_id="0781", product_id="5567",
                  manufacturer="SanDisk", product="Cruzer Blade",
                  serial="0xDEADBEEF"),
    ]
    with patch(
        "je_auto_control.utils.usb.list_usb_devices",
        return_value=_fake_enum(fake_devices),
    ):
        host = RemoteDesktopHost(
            token="t", bind="127.0.0.1", port=0, fps=30.0,
            frame_provider=_jpeg,
        )
        host.start()
        try:
            viewer = RemoteDesktopViewer(
                host="127.0.0.1", port=host.port, token="t",
            )
            viewer.connect(timeout=5.0)
            try:
                result = viewer.list_remote_usb_devices(timeout=3.0)
            finally:
                viewer.disconnect(timeout=1.0)
        finally:
            host.stop(timeout=1.0)
    assert result["backend"] == "fake"
    assert len(result["devices"]) == 2
    vendors = {d["vendor_id"] for d in result["devices"]}
    assert vendors == {"046d", "0781"}


def test_viewer_list_handles_empty_device_list():
    with patch(
        "je_auto_control.utils.usb.list_usb_devices",
        return_value=_fake_enum([]),
    ):
        host = RemoteDesktopHost(
            token="t", bind="127.0.0.1", port=0, fps=30.0,
            frame_provider=_jpeg,
        )
        host.start()
        try:
            viewer = RemoteDesktopViewer(
                host="127.0.0.1", port=host.port, token="t",
            )
            viewer.connect(timeout=5.0)
            try:
                result = viewer.list_remote_usb_devices(timeout=3.0)
            finally:
                viewer.disconnect(timeout=1.0)
        finally:
            host.stop(timeout=1.0)
    assert result == {"backend": "fake", "devices": []}


def test_viewer_list_handles_host_enumeration_failure():
    def boom():
        raise RuntimeError("usb backend down")

    with patch(
        "je_auto_control.utils.usb.list_usb_devices", side_effect=boom,
    ):
        host = RemoteDesktopHost(
            token="t", bind="127.0.0.1", port=0, fps=30.0,
            frame_provider=_jpeg,
        )
        host.start()
        try:
            viewer = RemoteDesktopViewer(
                host="127.0.0.1", port=host.port, token="t",
            )
            viewer.connect(timeout=5.0)
            try:
                result = viewer.list_remote_usb_devices(timeout=3.0)
            finally:
                viewer.disconnect(timeout=1.0)
        finally:
            host.stop(timeout=1.0)
    assert result["backend"] == "unavailable"
    assert result["devices"] == []


def test_list_remote_usb_raises_when_disconnected():
    viewer = RemoteDesktopViewer(host="127.0.0.1", port=1, token="t")
    with pytest.raises(RuntimeError):
        viewer.list_remote_usb_devices()


def test_list_remote_usb_times_out_when_host_silent(monkeypatch):
    """If the host never responds, the call must raise TimeoutError."""
    host = RemoteDesktopHost(
        token="t", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=_jpeg,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="t",
        )
        viewer.connect(timeout=5.0)
        try:
            # Patch the host's USB handler to be a no-op, so it never replies.
            from je_auto_control.utils.remote_desktop import host as host_mod

            def no_reply(self):
                return None

            monkeypatch.setattr(
                host_mod._ClientHandler, "_handle_usb_list_request",
                no_reply,
            )
            with pytest.raises(TimeoutError):
                viewer.list_remote_usb_devices(timeout=0.3)
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)
