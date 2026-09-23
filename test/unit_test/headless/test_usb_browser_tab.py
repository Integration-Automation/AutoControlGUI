"""Tests for the viewer-side USB browser helper (round 46)."""
import urllib.error

import pytest

# fetch_remote_devices is pure, but it lives next to a Qt widget that
# transitively pulls aiortc via gui/__init__.py. Skip the whole file
# unless the webrtc extra is installed.
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
pytest.importorskip("av")
pytest.importorskip("aiortc")

from je_auto_control.gui.usb_browser_tab import fetch_remote_devices  # noqa: E402
from je_auto_control.utils.rest_api.rest_server import RestApiServer  # noqa: E402


@pytest.fixture()
def rest_server(monkeypatch):
    # These tests cover the HTTP path, not this machine's USB hardware. The
    # real enumeration shells out to PowerShell on Windows, which under the
    # suite's redirected USERPROFILE rebuilds its module cache on every call
    # and outran the helper's 5 s timeout.
    from je_auto_control.utils.usb import usb_devices
    monkeypatch.setattr(usb_devices, "list_usb_devices", lambda: usb_devices.UsbEnumerationResult(
        backend="fake", devices=[usb_devices.UsbDevice(vendor_id="046d", product_id="c52b")]))
    server = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    server.start()
    yield server
    server.stop(timeout=1.0)


def test_fetch_returns_list_against_real_server(rest_server):
    host, port = rest_server.address
    # Loopback fixture URL — TLS termination happens at the reverse
    # proxy in production. These URLs never leave 127.0.0.1.
    devices = fetch_remote_devices(
        base_url=f"http://{host}:{port}",  # NOSONAR — loopback test fixture
        token=rest_server.token,
    )
    assert isinstance(devices, list)
    assert len(devices) == 1, "the stubbed device came through the REST route"
    for d in devices:
        assert isinstance(d, dict)
        for key in ("vendor_id", "product_id"):
            assert key in d


def test_fetch_rejects_missing_url():
    with pytest.raises(ValueError):
        fetch_remote_devices(base_url="", token="any")


def test_fetch_propagates_http_error(rest_server):
    """Wrong token surfaces the 401 as a urllib HTTPError."""
    host, port = rest_server.address
    with pytest.raises(urllib.error.HTTPError):
        fetch_remote_devices(
            base_url=f"http://{host}:{port}",  # NOSONAR — loopback test fixture
            token="not-the-token",
        )


def test_fetch_accepts_url_without_scheme(rest_server):
    host, port = rest_server.address
    # Bare host:port — the helper prepends http://.
    devices = fetch_remote_devices(
        base_url=f"{host}:{port}", token=rest_server.token,
    )
    assert isinstance(devices, list)


def test_fetch_strips_trailing_slash(rest_server):
    host, port = rest_server.address
    devices = fetch_remote_devices(
        base_url=f"http://{host}:{port}/",  # NOSONAR — loopback test fixture
        token=rest_server.token,
    )
    assert isinstance(devices, list)
